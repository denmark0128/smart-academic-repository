from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.utils.http import urlencode
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from urllib.parse import urlencode

import re
import os
import fitz
import json
from collections import Counter

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


def home(request):
    return render(request, 'home.html', {'name': 'John'})


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

def paper_list(request):
    query = request.GET.get('q')
    tag = request.GET.get('tag')
    college = request.GET.get('college')
    program = request.GET.get('program')
    year = request.GET.get('year')
    
    results = []
    papers = Paper.objects.all()

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
    if tag:
        papers = papers.filter(tags__contains=[tag])

    # === Get unique values for filters ===
    colleges = Paper.objects.values_list('college', flat=True).distinct()
    programs = Paper.objects.values_list('program', flat=True).distinct()
    years = Paper.objects.values_list('year', flat=True).distinct()
    years = sorted([y for y in years if y is not None], reverse=True)
    
    # === Build active filters ===
    active_filters = []
    for label, value, key in [
        ("College", college, "college"),
        ("Program", program, "program"),
        ("Year", year, "year"),
        ("Tag", tag, "tag"),
    ]:
        if value:
            active_filters.append({
                "label": label,
                "value": value,
                "remove_url": urlencode({k:v for k,v in request.GET.items() if k != key})
            })

    # === Searching ===
    if query:
        try:
            # Keyword search first
            search_results = keyword_search(query, top_k=5)

            if not search_results:
                # Use the custom semantic_search function with filters
                search_results = semantic_search(
                    query,
                    top_k=5,
                    college=college,
                    program=program,
                    year=year,
                    tag=tag
                )

            # Convert into results list
            for res in search_results:
                paper_obj = Paper.objects.filter(pk=res.get("paper_id")).first()
                results.append({
                    "query": query,
                    "paper": paper_obj,
                    "snippet": res.get("text", ""),
                    "tags": paper_obj.tags if paper_obj else [],
                    "score": f"{res.get('score', '-'):.3f}",
                    "page": res.get("page"),
                })

        except Exception as e:
            # Fallback to naive filter if embeddings/index missing
            papers = Paper.objects.filter(
                Q(title__icontains=query) | Q(abstract__icontains=query)
            )
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
            
    paginator = Paginator(results, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

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
        "active_filters": active_filters,
    }

    if request.htmx:
        return render(request, "papers/partials/_paper_list_content.html", context)
    return render(request, "papers/paper_list.html", context)


def paper_detail(request, pk):
    paper = get_object_or_404(Paper, pk=pk)

    # PDF viewer
    pdf_url = request.build_absolute_uri(paper.file.url)
    viewer_url = f"{settings.STATIC_URL}pdfjs/web/viewer.html?file={pdf_url}"

    # Citations & saved state
    matched_citations = paper.matched_citations.select_related("matched_paper")
    matched_citation_count = matched_citations.count()
    citations_pointing_here = MatchedCitation.objects.filter(matched_paper=paper).select_related("source_paper")
    citation_count = citations_pointing_here.count()
    is_saved = SavedPaper.objects.filter(user=request.user, paper=paper).exists()

    return render(request, 'papers/paper_detail.html', {
        'paper': paper,
        'tags': paper.tags,
        'citations_pointing_here': citations_pointing_here,
        'citation_count': citation_count,
        'college': paper.college,
        'program': paper.program,
        'matched_citations': matched_citations,
        'matched_citation_count': matched_citation_count,
        'viewer_url': viewer_url,
        'is_saved': is_saved,
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

    return render(request, 'papers/paper_insights.html', {
        'tag_counts': tag_counts,
        'tag_labels_json': json.dumps(tag_labels),
        'tag_values_json': json.dumps(tag_values)
    })


def upload_tab(request):
    return render(request, "papers/partials/uploads/upload_form.html")

def processing_tab(request):
    return render(request, "papers/partials/uploads/processing_tab.html")

def review_tab(request):
    return render(request, "papers/partials/uploads/review_tab.html")
   