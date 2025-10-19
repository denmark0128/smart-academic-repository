from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.core.cache import cache
from django.utils.html import escape
from django.conf import settings
from django.utils.http import urlencode
from django.db.models import Q, Min, Max, Count, Prefetch, Sum, F
from django.contrib.auth.decorators import login_required
from urllib.parse import urlencode
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


import re
import os
import fitz
import json
import random
from collections import Counter
from random import randint

from papers.models import Paper, PaperChunk, SavedPaper, MatchedCitation
from papers.forms import PaperForm
from papers.utils.nlp import extract_tags
from utils.semantic_search import semantic_search, keyword_search, index_paper, get_model
from utils.metadata_extractor import (
    extract_metadata as extract_metadata_from_pdf,
    normalize_college,
    normalize_program,
)
from utils.related import find_related_papers

from utils.single_paper_rag import query_rag

def random_paper_redirect(request):
    max_id = Paper.objects.aggregate(max_id=Max('id'))['max_id']
    if not max_id:
        return redirect('paper_list')

    while True:
        random_id = randint(1, max_id)
        paper = Paper.objects.filter(id=random_id).first()
        if paper:
            break

    return redirect('paper_detail', pk=paper.id)

def home(request):
    paper = Paper.objects.order_by('?').first()
    return render(request, "home.html", {"random_paper": paper})



def papers_view(request):
    if request.headers.get('Hx-Request') == 'true':
        return render(request, "partials/papers.html")  # just content
    return render(request, "papers.html")  # full layout

def extract_matching_snippet(text, query):
    # Split text into sentences or paragraphs
    paragraphs = re.split(r'(?<=[.!?])\s+|\n+', text)
    for p in paragraphs:
        if query.lower() in p.lower():
            # Highlight match using a regex, case-insensitive
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            highlighted = pattern.sub(r'<mark>\g<0></mark>', p)
            return highlighted.strip()
    return ""


def highlight_text(text, query):
    """Escape and highlight occurrences of query inside text (case-insensitive)."""
    if not text:
        return ""
    try:
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        return pattern.sub(r'<mark>\g<0></mark>', escape(text))
    except Exception:
        return escape(text)


def autocomplete(request):
    """Return JSON suggestions for titles and authors.

    GET params:
      - q: query string
      - limit: optional integer (max suggestions, default 10)
    """
    q = (request.GET.get('q') or '').strip()

    # detect HTMX early so we can return an empty fragment (no-swap) when there's no query
    try:
        is_htmx = bool(request.htmx)
    except Exception:
        is_htmx = request.headers.get('Hx-Request') == 'true'

    if not q:
        # If HTMX request, show recent papers/authors from session (if any)
        recent_papers = []
        recent_authors = []
        try:
            rp_ids = request.session.get('recent_papers', [])[:5]
            if rp_ids:
                # fetch paper titles and preserve order
                papers_qs = Paper.objects.filter(id__in=rp_ids)
                id_to_title = {p.id: p.title for p in papers_qs}
                for pid in rp_ids:
                    title = id_to_title.get(pid)
                    if title:
                        recent_papers.append({'paper_id': pid, 'value': title, 'display': escape(title)})

            ra = request.session.get('recent_authors', [])[:5]
            for a in ra:
                recent_authors.append({'value': a, 'display': escape(a)})
        except Exception:
            pass

        if is_htmx and (recent_papers or recent_authors):
            return render(request, 'partials/autocomplete_list.html', {
                'papers': recent_papers,
                'authors': recent_authors,
                'query': q,
            })

        # Fallback: no recent items — return 204 so nothing shows
        return HttpResponse(status=204)

    try:
        limit = int(request.GET.get('limit', 10))
    except Exception:
        limit = 10

    # Per-section hard limit (user requested 5 per section)
    per_section_limit = 5

    cache_key = f"autocomplete:{q.lower()}:{limit}"
    results = None
    try:
        results = cache.get(cache_key)
    except Exception:
        results = None

    if results is not None:
        # cached structure is expected to be {'papers': [...], 'authors': [...]}
        if is_htmx:
            return render(request, 'partials/autocomplete_list.html', {
                'papers': results.get('papers', []),
                'authors': results.get('authors', []),
                'query': q,
            })
        return JsonResponse(results)

    # Build separate lists for papers and authors
    papers_list = []
    authors_list = []

    # 1) Titles (exact substring match) - up to `limit` results
    title_qs = Paper.objects.filter(title__icontains=q).values('id', 'title')[:limit]
    for t in title_qs:
        papers_list.append({
            'paper_id': t['id'],
            'value': t['title'],
            'display': highlight_text(t['title'], q),
        })

    # 2) Authors (search in JSON list; fall back to Python-side filter)
    if True:
        candidate_qs = Paper.objects.exclude(authors__isnull=True).values('id', 'authors')[:1000]
        seen_authors = set()
        for item in candidate_qs:
            authors = item.get('authors') or []
            for a in authors:
                if not isinstance(a, str):
                    continue
                if q.lower() in a.lower() and a not in seen_authors:
                    seen_authors.add(a)
                    authors_list.append({
                        'value': a,
                        'display': highlight_text(a, q),
                    })
                    if len(authors_list) >= limit:
                        break
            if len(authors_list) >= limit:
                break

    # trim and package
    papers_list = papers_list[:per_section_limit]
    authors_list = authors_list[:per_section_limit]

    res_struct = {'papers': papers_list, 'authors': authors_list}
    try:
        cache.set(cache_key, res_struct, timeout=30)
    except Exception:
        pass

    if is_htmx:
        return render(request, 'partials/autocomplete_list.html', {
            'papers': papers_list,
            'authors': authors_list,
            'query': q,
        })

    return JsonResponse(res_struct)

def paper_list(request):
    query = request.GET.get('q')
    author_filter = request.GET.get('author')
    tags = request.GET.getlist('tag')  # multiple tags
    college = request.GET.get('college')
    program = request.GET.get('program')
    year = request.GET.get('year')

    results = []

    # === Fetch tags efficiently (no heavy fields) ===
    tag_data = Paper.objects.only('tags').values_list('tags', flat=True)
    all_tags = []
    for tlist in tag_data:
        if isinstance(tlist, list):
            all_tags.extend(tlist)
    tag_counts = dict(Counter(all_tags))


    # === Base queryset — defer heavy fields ===
    papers = Paper.objects.defer(
        'title_embedding', 'abstract_embedding', 'summary', 'file'
    ).all()

    # === Apply filters ===
    if college:
        papers = papers.filter(college=college)
    if program:
        papers = papers.filter(program=program)
    if year:
        try:
            papers = papers.filter(year=int(year))
        except (ValueError, TypeError):
            pass

    # === Additive multi-tag filtering (OR) ===
    if tags:
        tag_filters = Q()
        for t in tags:
            tag_filters |= Q(tags__contains=[t])
        papers = papers.filter(tag_filters)

    # === Get unique values for filters ===
    colleges = Paper.objects.values_list('college', flat=True).distinct()
    programs = Paper.objects.values_list('program', flat=True).distinct()
    years = Paper.objects.values_list('year', flat=True).distinct()
    years = sorted([y for y in years if y is not None], reverse=True)

    # === Build active filters ===
    active_filters = []
    # College / Program / Year
    for label, value, key in [
        ("College", college, "college"),
        ("Program", program, "program"),
        ("Year", year, "year"),
    ]:
        if value:
            query_dict = request.GET.copy()
            query_dict.pop(key, None)
            active_filters.append({
                "label": label,
                "value": value,
                "remove_url": query_dict.urlencode()
            })

    # Tags (individual pills)
    for t in tags:
        remaining_tags = [x for x in tags if x != t]
        query_dict = request.GET.copy()
        query_dict.setlist('tag', remaining_tags)
        active_filters.append({
            "label": "Tag",
            "value": t,
            "remove_url": query_dict.urlencode()
        })

    # === Searching ===
    if query:
        try:
            if author_filter:
                papers_by_author = Paper.objects.filter(authors__contains=[author_filter])[:10]
                for paper in papers_by_author:
                    snippet = extract_matching_snippet(paper.abstract or paper.summary or '', query or author_filter)
                    results.append({
                        "query": query,
                        "paper": paper,
                        "snippet": snippet,
                        "tags": paper.tags,
                        "score": '-',
                        "page": None,
                    })
                search_results = []
            else:
                search_results = keyword_search(query, top_k=5)

            if not search_results:
                search_results = semantic_search(query, top_k=5)

            for res in search_results:
                paper_obj = Paper.objects.filter(pk=res.get("paper_id")).first()
                score = res.get('score')
                results.append({
                    "query": query,
                    "paper": paper_obj,
                    "snippet": res.get("text", ""),
                    "tags": paper_obj.tags if paper_obj else [],
                    "score": f"{score:.3f}" if isinstance(score, (int, float)) else "-",
                    "page": res.get("page"),
                })

        except Exception as e:
            import traceback
            traceback.print_exc()
            papers = Paper.objects.filter(Q(title__icontains=query) | Q(abstract__icontains=query))
            for paper in papers:
                snippet = extract_matching_snippet(paper.abstract, query)
                results.append({
                    "query": query,
                    "paper": paper,
                    "snippet": snippet,
                    "tags": paper.tags,
                })
    else:
        for paper in papers:
            results.append({
                "query": query,
                "paper": paper,
                "snippet": "",
                "tags": paper.tags,
            })

    # === Pagination ===
    paginator = Paginator(results, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    view_mode = request.GET.get('view_mode', 'card')
    saved_paper_ids = []
    if request.user.is_authenticated:
        saved_paper_ids = list(request.user.saved_papers.values_list('paper_id', flat=True))

    # pass this info to template
    for paper in papers:
        paper.is_saved = paper.id in saved_paper_ids
    context = {
        "results": results,
        "query": query,
        "page_obj": page_obj,
        "colleges": colleges,
        "programs": programs,
        "years": years,
        "selected_college": college,
        "selected_program": program,
        "selected_year": year,
        "selected_tags": tags,
        "active_filters": active_filters,
        "tag_counts": tag_counts,
        "view_mode": view_mode,
        "saved_paper_ids": saved_paper_ids,
    }

    if request.htmx:
        return render(request, "papers/partials/paper_list/_paper_list_content.html", context)
    return render(request, "papers/paper_list.html", context)



def paper_detail(request, pk):
    paper = (
        Paper.objects
        .prefetch_related(
            Prefetch(
                "matched_citations",
                queryset=MatchedCitation.objects.select_related("matched_paper")
            ),
            Prefetch(
                "reverse_matched_citations",
                queryset=MatchedCitation.objects.select_related("source_paper")
            )
        )
        .get(pk=pk)
    )

    # === PDF Viewer ===
    pdf_url = request.build_absolute_uri(paper.file.url)
    viewer_url = f"{settings.STATIC_URL}pdfjs/web/viewer.html?file={pdf_url}"

    # === Figures ===
    paper_dir = os.path.join(settings.MEDIA_ROOT, f"extracted/paper_{paper.id}")
    paper_folder = os.path.join(settings.MEDIA_URL, f"extracted/paper_{paper.id}")
    figures = [
        {"url": os.path.join(paper_folder, fname), "page_number": None}
        for fname in os.listdir(paper_dir)
    ] if os.path.exists(paper_dir) else []

    # === Citations ===
    matched_citations = list(paper.matched_citations.all())
    citations_pointing_here = list(paper.reverse_matched_citations.all())

    citation_count = paper.citation_count_cached
    matched_citation_count = paper.matched_count_cached

    # === Saved State ===
    is_saved = (
        request.user.is_authenticated
        and SavedPaper.objects.filter(paper=paper, user=request.user).exists()
    )

    # === Track recently viewed papers/authors ===
    try:
        recent_papers = request.session.get('recent_papers', [])
        if paper.id in recent_papers:
            recent_papers.remove(paper.id)
        recent_papers.insert(0, paper.id)
        request.session['recent_papers'] = recent_papers[:10]

        recent_authors = request.session.get('recent_authors', [])
        for a in (paper.authors or []):
            if isinstance(a, str):
                if a in recent_authors:
                    recent_authors.remove(a)
                recent_authors.insert(0, a)
        request.session['recent_authors'] = recent_authors[:20]
    except Exception:
        pass  # don’t break if sessions fail

    from django.db import models
    Paper.objects.filter(pk=paper.pk).update(views=models.F('views') + 1)

    # === Render ===
    return render(request, "papers/paper_detail.html", {
        "paper": paper,
        "tags": paper.tags,
        "citations_pointing_here": citations_pointing_here,
        "citation_count": citation_count,
        "college": paper.college,
        "program": paper.program,
        "matched_citations": matched_citations,
        "matched_citation_count": matched_citation_count,
        "viewer_url": viewer_url,
        "is_saved": is_saved,
        "figures": figures,
    })

def paper_query(request, pk):
    """HTMX endpoint for paper Q&A chatbot"""
    if request.method == "POST":
        paper = get_object_or_404(Paper, pk=pk)
        user_query = request.POST.get("query", "").strip()
        if not user_query:
            return JsonResponse({"error": "Empty query"}, status=400)

        # Use prototype query_rag
        answer = query_rag(user_query, top_k=3)

        # Return HTMX snippet
        return render(request, "papers/partials/answer.html", {"answer": answer})

    return JsonResponse({"error": "POST required"}, status=400)

@login_required
def paper_upload(request):
    papers = Paper.objects.filter(uploaded_by=request.user).order_by("-uploaded_at")
    years = Paper.objects.values_list('year', flat=True).distinct().order_by('-year')

    if request.method == 'POST':
        form = PaperForm(request.POST, request.FILES)
        if form.is_valid(): 
            paper = form.save(commit=False)
            paper.uploaded_by = request.user
            paper.is_indexed = False  # Initially set to False
            
            # Extract tags from abstract
            tags = extract_tags(
                (paper.title or "") + " " +
                (paper.abstract or "") + " " +
                (paper.summary or "")
            )
            paper.tags = tags
            paper.save()

            # --- Auto-summary ---
            if paper.file:
                try:
                    model = get_model()
                    if paper.title:
                        paper.title_embedding = model.encode(paper.title).tolist()
                    if paper.abstract:
                        paper.abstract_embedding = model.encode(paper.abstract).tolist()
                    paper.save(update_fields=['title_embedding', 'abstract_embedding'])
                except Exception as e:
                    import traceback
                    print(f"[Metadata Embedding Error] {e}")
                    traceback.print_exc()
                try:
                    from utils.summarize import extract_text_from_pdf, summarize_text
                    text = extract_text_from_pdf(paper.file.path)
                    summary = summarize_text(text)
                    paper.summary = summary
                    paper.save(update_fields=['summary'])
                except Exception as e:
                    import traceback
                    print(f"[Summary Error] {e}")
                    traceback.print_exc()

                try:
                    # --- Embed chunks directly into PaperChunk ---
                    from utils.semantic_search import index_paper
                    index_paper(paper)  # ✅ pass the Paper instance
                    paper.is_indexed = True
                    paper.save(update_fields=['is_indexed'])
                except Exception as e:
                    import traceback
                    print(f"[Embedding Error] {e}")
                    traceback.print_exc()

            return redirect('/papers/upload?status=success')
    else:
        form = PaperForm()

    status = request.GET.get('status')
    return render(
        request,
        'papers/paper_upload.html',
        {'form': form, 'status': status, 'papers': papers, 'years': years}
    )


@login_required
def profile_page(request):
    return render(request, 'profile/show.html', {'user': request.user})

@login_required
def save_paper(request, paper_id):
    paper = get_object_or_404(Paper, id=paper_id)
    SavedPaper.objects.get_or_create(user=request.user, paper=paper)
    
    if request.htmx:  # htmx request
        return render(request, 'partials/_save_button.html', {
            'paper': paper,
            'is_saved': True
        })
    return redirect(request.META.get('HTTP_REFERER', 'paper_detail', pk=paper_id))


@login_required
def unsave_paper(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    SavedPaper.objects.filter(user=request.user, paper=paper).delete()
    
    if request.htmx:
        return render(request, 'partials/_save_button.html', {
            'paper': paper,
            'is_saved': False
        })
    return JsonResponse({'status': 'unsaved'})

@login_required
def toast(request):
    message = request.GET.get('message', '')
    return render(request, 'partials/_toast.html', {'message': message})


@login_required
def saved_papers(request):
    saved = SavedPaper.objects.filter(user=request.user).select_related('paper')
    return render(request, 'profile/saved_papers.html', {'saved_papers': saved})

def pdf_viewer(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    return render(request, 'papers/pdf_reader.html', {
        'pdf_url': paper.pdf_file.url  # e.g., "/media/papers/sample.pdf"
    })

def extract_metadata(request):
    if request.method == "POST":
        uploaded_file = request.FILES.get("file")

        if not uploaded_file:
            return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

        # Save the uploaded file temporarily
        temp_path = os.path.join(settings.MEDIA_ROOT, "temp_upload.pdf")
        with open(temp_path, "wb+") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        try:
            # Extract structured metadata instead of raw text
            metadata = extract_metadata_from_pdf(temp_path)

            raw_college = metadata.get("college", "")
            raw_program = metadata.get("program", "")

            metadata["college"] = normalize_college(raw_college)
            metadata["program"] = normalize_program(raw_program)

            return JsonResponse({
                "success": True,
                "metadata": metadata
            })
        except Exception as e:
            return JsonResponse({
                "success": False,
                "error": str(e)
            }, status=500)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    return JsonResponse({
        "success": False,
        "error": "Only POST method allowed"
    }, status=405)

    

def paper_insights(request):
    papers = Paper.objects.all()
    tags = [tag for paper in papers for tag in paper.tags]
    tag_counts = dict(Counter(tags))

    tag_labels = list(tag_counts.keys())
    tag_values = list(tag_counts.values())

    # Trend: number of papers per year
    years = sorted({p.year for p in papers if p.year})
    year_counts = {y: 0 for y in years}
    for p in papers:
        if p.year:
            year_counts[p.year] = year_counts.get(p.year, 0) + 1
    year_labels = years
    year_values = [year_counts.get(y, 0) for y in year_labels]

    # Top authors by number of papers and compute average citations per author
    # Map paper_id -> citation count
    paper_cite_counts = {}
    cite_qs = MatchedCitation.objects.values('matched_paper').annotate(c=Count('id'))
    for row in cite_qs:
        pid = row.get('matched_paper')
        if pid:
            paper_cite_counts[pid] = row.get('c', 0)

    author_to_papers = {}
    for p in papers:
        for a in (p.authors or []):
            if not isinstance(a, str):
                continue
            author_to_papers.setdefault(a, []).append(p.id)

    author_stats = []
    for a, pids in author_to_papers.items():
        counts = [paper_cite_counts.get(pid, 0) for pid in pids]
        total = sum(counts)
        avg = (total / len(counts)) if counts else 0
        author_stats.append((a, len(pids), avg))

    # Top authors by number of papers (for bar chart) and by avg citations
    top_by_count = sorted(author_stats, key=lambda x: x[1], reverse=True)[:10]
    author_labels = [a for a, n, avg in top_by_count]
    author_values = [n for a, n, avg in top_by_count]

    top_by_avg = sorted([s for s in author_stats if s[1] > 0], key=lambda x: x[2], reverse=True)[:10]
    avg_author_labels = [a for a, n, avg in top_by_avg]
    avg_author_values = [round(avg, 2) for a, n, avg in top_by_avg]

    # Tag trend over time: pick top tags and compute counts per year
    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_tag_names = [t for t, _ in top_tags]
    tag_trends = {}
    for tag in top_tag_names:
        counts = []
        for y in year_labels:
            c = Paper.objects.filter(year=y, tags__contains=[tag]).count()
            counts.append(c)
        tag_trends[tag] = counts

    # Papers by college/program: choose top programs and compute counts per college
    programs = [p.program for p in papers if p.program]
    prog_counts = Counter(programs)
    top_programs = [p for p,c in prog_counts.most_common(5)]
    colleges = sorted(set([p.college for p in papers if p.college]))
    college_program_matrix = []
    for college in colleges:
        row = []
        for prog in top_programs:
            row.append(Paper.objects.filter(college=college, program=prog).count())
        college_program_matrix.append({
            'college': college,
            'counts': row,
        })

    insights = {
        'tag_labels': tag_labels,
        'tag_values': tag_values,
        'year_labels': year_labels,
        'year_values': year_values,
        'author_labels': author_labels,
        'author_values': author_values,
        'avg_author_labels': avg_author_labels,
        'avg_author_values': avg_author_values,
        'tag_trends': tag_trends,
        'top_tag_names': top_tag_names,
        'programs': top_programs,
        'colleges': colleges,
        'college_program_matrix': college_program_matrix,
        # papers per college
        'college_labels': colleges,
        'college_values': [Paper.objects.filter(college=c).count() for c in colleges],
    }

    # Top cited papers (ordered)
    top_cited = []
    cite_qs2 = MatchedCitation.objects.values('matched_paper').annotate(c=Count('id')).order_by('-c')[:10]
    top_ids = [r['matched_paper'] for r in cite_qs2 if r.get('matched_paper')]
    if top_ids:
        papers_map = {p.id: p.title for p in Paper.objects.filter(id__in=top_ids)}
        for r in cite_qs2:
            pid = r.get('matched_paper')
            if not pid:
                continue
            title = papers_map.get(pid)
            if title:
                top_cited.append({'paper_id': pid, 'title': title, 'count': r.get('c', 0)})

    return render(request, 'papers/paper_insights.html', {
        'tag_counts': tag_counts,
        'insights_json': json.dumps(insights),
        'top_cited_papers': top_cited,
        'total_papers': Paper.objects.count(),
        'total_citations': Paper.objects.aggregate(Sum('citation_count_cached'))['citation_count_cached__sum'] or 0,
        'top_cited_paper': Paper.objects.order_by('-citation_count_cached').first(),
    })


def upload_tab(request):
    return render(request, "papers/partials/uploads/upload_form.html")

def processing_tab(request):
    return render(request, "papers/partials/uploads/processing_tab.html")

def review_tab(request):
    return render(request, "papers/partials/uploads/review_tab.html")
   