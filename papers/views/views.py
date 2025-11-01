from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.core.cache import cache
from django.utils.html import escape
from django.conf import settings
from django.utils.http import urlencode
from django.db.models import Count, Sum
from django.contrib.auth.decorators import login_required
from urllib.parse import urlencode
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.views.decorators.cache import cache_page

import re
import os
import fitz
import json
import random
from collections import Counter
from random import randint

from papers.models import Paper, SavedPaper, MatchedCitation, Tag
from papers.forms import PaperForm
from papers.utils.nlp import extract_tags, get_mpnet_model
from utils.extract_metadata_from_abstract import extract_metadata_from_abstract
from utils.chm_to_html import merge_chm_to_html
from utils.metadata_extractor import (
    extract_metadata as extract_metadata_from_pdf,
    normalize_college,
    normalize_program,
)
from utils.summarize import generate_summary
from utils.related import find_related_papers

from utils.single_paper_rag import query_rag

def home(request):
    return render(request, "home.html")


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
    # Extract filters, query, tags, college, program, year like before
    query = request.GET.get('q')
    author_filter = request.GET.get('author')
    tags = request.GET.getlist('tag')
    college = request.GET.get('college')
    program = request.GET.get('program')
    year = request.GET.get('year')
    view_mode = request.GET.get('view_mode', 'card')

    # Build base context: filters, tag counts, view_mode, etc.

    context = {
        "query": query,
        "selected_college": college,
        "selected_program": program,
        "selected_year": year,
        "selected_tags": tags,
        "view_mode": view_mode,
    }

    # The **full page** just contains filters, container, skeleton, etc.
    return render(request, "papers/paper_list.html", context)


@cache_page(30 * 1, key_prefix='paper_detail_public')  # Cache for all users
def paper_detail(request, pk):
    """
    Main paper detail view - loads instantly with minimal data.
    Only fetches fields needed for initial render (title, authors, year, college, program).
    Everything else deferred to partials view.
    """

    paper = Paper.objects.only(
        'id',
        'title', 
        'authors', 
        'year', 
        'college', 
        'program',
        'file',
        'views',      # ← Add this
        'local_doi',  
    ).get(pk=pk)
    
    context = {
        'paper': paper,
    }
    
    return render(request, 'papers/paper_detail.html', context)

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
    print("[1] Entered paper_upload view")
    papers = Paper.objects.filter(uploaded_by=request.user).order_by("-uploaded_at")
    years = Paper.objects.values_list("year", flat=True).distinct().order_by("-year")

    if request.method == "POST":
        print("[2] POST request detected")
        form = PaperForm(request.POST, request.FILES)

        if form.is_valid():
            print("[3] Form is valid")
            paper = form.save(commit=False)
            paper.uploaded_by = request.user
            paper.is_indexed = False
            paper.status = "processing"
            paper.save()
            print(f"[4] Saved new Paper object with ID {paper.id}")

            ext = os.path.splitext(paper.file.name)[1].lower()
            print(f"[5] Uploaded file extension: {ext}")

            # --- PDF / DOCX ---
            if ext in [".pdf", ".docx"]:
                print("[6] Processing PDF/DOCX")
                try:
                    metadata = extract_metadata(paper.file.path)
                    print(f"[7] Extracted metadata: {metadata}")

                    paper.title = metadata.get("title") or paper.title
                    paper.abstract = metadata.get("abstract") or paper.abstract
                    paper.authors = metadata.get("authors") or paper.authors
                    paper.college = metadata.get("college") or paper.college
                    paper.program = metadata.get("program") or paper.program

                    year_list = metadata.get("year")
                    print(f"[8] Year list: {year_list}")
                    if year_list and len(year_list) > 0:
                        try:
                            paper.year = int(year_list[0])
                        except ValueError:
                            print(f"[PDF Metadata] Invalid year: {year_list[0]}")

                    paper.save(update_fields=["title", "abstract", "authors", "college", "program", "year"])
                    print("[9] Saved Paper metadata for PDF/DOCX")
                except Exception as e:
                    print(f"[PDF Metadata Error] {e}")

            # --- CHM ---
            elif ext == ".chm":
                print("[10] Processing CHM")
                try:
                    merged_html_path, _ = merge_chm_to_html(
                        paper.file.path, settings.MEDIA_ROOT
                    )
                    print(f"[11] CHM merged HTML path: {merged_html_path}")

                    # Save relative path to model (for later access by index_paper)
                    paper.merged_html.name = str(merged_html_path).replace(str(settings.MEDIA_ROOT), "").replace("\\", "/").lstrip("/")
                    paper.save(update_fields=["merged_html"])
                    print("[12] Saved merged_html FileField")
                except Exception as e:
                    print(f"[CHM Merge Error] {e}")

                # Extract metadata from merged.html
                try:
                    if os.path.exists(merged_html_path):
                        metadata = extract_metadata_from_abstract(merged_html_path)
                        print(f"[13] Extracted CHM metadata: {metadata}")

                        paper.title = metadata.get("title") or paper.title
                        paper.abstract = metadata.get("description") or paper.abstract
                        paper.authors = metadata.get("authors") or paper.authors

                        year = metadata.get("year")
                        if year:
                            try:
                                paper.year = int(year)
                            except ValueError:
                                print(f"[CHM Metadata] Invalid year: {year}")

                        paper.save(update_fields=["title", "abstract", "authors", "year"])
                        print("[15] Saved Paper metadata for CHM")
                except Exception as e:
                    print(f"[CHM Metadata Error] {e}")

            # --- POST-PROCESSING PIPELINE ---
            
            # 1. Semantic Search Indexing (creates embeddings + chunks)
            try:
                print("[16] Indexing paper for semantic search")
                from utils.semantic_search import index_paper
                index_paper(paper)
                paper.is_indexed = True
                paper.save(update_fields=["is_indexed"])
                print("[17] Paper indexed successfully")
            except Exception as e:
                print(f"[Indexing Error] {e}")

            # 2. Tag/Keyword Extraction
            try:
                # 1) get plain text to pass to tagger (reuse your helper from staff_paper_regenerate_tags)
                text_for_tagging = _get_paper_text_for_tagging(paper)
                if not text_for_tagging.strip():
                    print("[19] No text available for tagging")
                else:
                    # 2) call extract_tags correctly (pass text, not the Paper)
                    # adjust top_n/min_score to taste
                    from papers.utils.nlp import extract_tags
                    tag_names = extract_tags(text_for_tagging, top_n=6, min_score=0.45)

                    if not tag_names:
                        print("[19] extract_tags returned no tags")
                    else:
                        print(f"[19] Tags extracted: {tag_names}")

                        # 3) ensure Tag rows exist and have embeddings (same pattern as your working code)
                        model = get_mpnet_model()
                        for tag_name in tag_names:
                            tag, created = Tag.objects.get_or_create(
                                name=tag_name,
                                defaults={"is_active": True}
                            )
                            if tag.embedding is None:
                                try:
                                    emb = model.encode(tag.name, convert_to_numpy=True)
                                    tag.embedding = emb
                                    tag.save(update_fields=["embedding"])
                                    print(f"[19] Generated embedding for tag: {tag.name}")
                                except Exception as e:
                                    print(f"[19] Embedding error for {tag.name}: {e}")

                        # 4) save as JSONField list of strings
                        paper.tags = tag_names
                        paper.save(update_fields=["tags"])
                        print(f"[19] Tags saved to paper.tags: {tag_names}")

            except Exception as e:
                # print full traceback to help debugging
                import traceback
                print(f"[Tag Extraction Error] {e}")
                traceback.print_exc()

            # 3. Summary Generation
            try:
                print("[3] Generating summary using local Llama model...")
                summary = generate_summary(paper)  # 👈 call it here

                if summary:
                    paper.summary = summary  # save to model if you have a field
                    paper.save(update_fields=["summary"])
                    print("[3] ✅ Summary generated and saved.")
                else:
                    print("[3] ⚠️ No summary generated.")
            except Exception as e:
                print(f"[3] ❌ Summary generation failed: {e}")
            
            # 4. Citation Extraction and Matching
            try:
                print("[22] Extracting and matching citations")
                from utils.citation_matcher import extract_and_match_citations
                
                # This function will:
                # - Extract citations from the paper text
                # - Match them against existing papers in database
                # - Create MatchedCitation records
                matched_citations = extract_and_match_citations(paper)
                
                # Update cached citation counts
                paper.matched_count_cached = len(matched_citations)
                paper.save(update_fields=["matched_count_cached"])
                
                print(f"[23] Found and saved {len(matched_citations)} citations")
            except Exception as e:
                print(f"[Citation Matching Error] {e}")

            # Mark processing complete
            try:
                paper.status = "complete"
                paper.save(update_fields=["status"])
                print("[24] All processing complete - status set to 'complete'")
            except Exception as e:
                print(f"[Status Update Error] {e}")

            return redirect("/papers/upload?status=success")
        else:
            print("[3a] Form is invalid")
            print(form.errors)

    else:
        print("[2a] GET request detected")
        form = PaperForm()

    status = request.GET.get("status")
    print(f"[25] Rendering template with status: {status}")
    return render(request, "papers/paper_upload.html", {
        "form": form,
        "status": status,
        "papers": papers,
        "years": years,
    })


def _get_paper_text_for_tagging(paper):
    """Helper to safely extract text from paper for tagging"""
    text_parts = []
    
    if paper.title:
        text_parts.append(str(paper.title))
    
    if paper.abstract:
        text_parts.append(str(paper.abstract))
    
    if paper.authors:
        if isinstance(paper.authors, (list, tuple)):
            text_parts.append(" ".join(str(a) for a in paper.authors))
        else:
            text_parts.append(str(paper.authors))
    
    return " ".join(text_parts)

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
def save_paper_list(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    
    # Your logic to save the paper for the user
    SavedPaper.objects.get_or_create(user=request.user, paper=paper)
    
    # Create the context for the *new* state
    context = {
        'paper': paper,
        'is_saved': True  # The new state is 'saved'
    }
    
    # Return the rendered partial, not the whole page
    return render(request, 'partials/save_button_list.html', context)

@login_required
def unsave_paper_list(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    
    # Your logic to unsave the paper
    SavedPaper.objects.filter(user=request.user, paper=paper).delete()
    
    # Create the context for the *new* state
    context = {
        'paper': paper,
        'is_saved': False  # The new state is 'not saved'
    }
    
    # Return the rendered partial
    return render(request, 'partials/save_button_list.html', context)


@login_required
def toast(request):
    message = request.GET.get('message', '')
    return render(request, 'partials/_toast.html', {'message': message})


@login_required
def saved_papers(request):
    return render(request, 'profile/saved_papers.html')

def pdf_viewer(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    return render(request, 'papers/pdf_reader.html', {
        'pdf_url': paper.pdf_file.url  # e.g., "/media/papers/sample.pdf"
    })

def extract_metadata(request):
    print("[Extract Metadata] Entered view")  # DEBUG
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Only POST method allowed"}, status=405)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

    filename = uploaded_file.name
    ext = os.path.splitext(filename)[1].lower()
    temp_path = os.path.join(settings.MEDIA_ROOT, f"temp_upload_{filename}")
    print(f"[Extract Metadata] Saving temp file to {temp_path}")  # DEBUG

    try:
        with open(temp_path, "wb+") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        metadata = {}
        if ext in [".pdf", ".docx"]:
            print("[Extract Metadata] PDF/DOCX detected, extracting metadata...")  # DEBUG
            metadata = extract_metadata_from_pdf(temp_path)

        elif ext == ".chm":
            print("[Extract Metadata] CHM detected, merging CHM...")  # DEBUG
            merged_html_path, _ = merge_chm_to_html(temp_path, settings.MEDIA_ROOT)
            print(f"[Extract Metadata] CHM merged to {merged_html_path}")  # DEBUG
            metadata = extract_metadata_from_abstract(merged_html_path)
            print(f"[Extract Metadata] CHM metadata extracted: {metadata}")  # DEBUG

        # Normalize college/program
        raw_college = metadata.get("college", "")
        raw_program = metadata.get("program", "")

        metadata["college"] = normalize_college(raw_college)
        metadata["program"] = normalize_program(raw_program)

        print(f"[Extract Metadata] Final metadata: {metadata}")  # DEBUG
        return JsonResponse({"success": True, "metadata": metadata})

    except Exception as e:
        print(f"[Extract Metadata ERROR] {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
            print("[Extract Metadata] Temp file removed")  # DEBUG
    

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
   