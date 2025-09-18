from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.utils.http import urlencode
from django.db.models import Q
from django.contrib.auth.decorators import login_required

import re
import os
import fitz
import json
from collections import Counter

from papers.models import Paper, SavedPaper, MatchedCitation
from papers.forms import PaperForm
from papers.utils.nlp import extract_tags
from utils.semantic_search import semantic_search, keyword_search, index_paper
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
    results = []
    papers = Paper.objects.all()

    if query:
        # Use keyword search first
        try:
            search_results = keyword_search(query, top_k=5)
            if not search_results:
                # Fallback to semantic search if keyword search returns nothing
                search_results = semantic_search(query, top_k=5, min_score=0.25)
            for res in search_results:
                paper_obj = None
                # Try to match by paper_id if available
                paper_id = res.get('paper_id')
                if paper_id:
                    paper_obj = Paper.objects.filter(pk=paper_id).first()
                # Fallback to title and author matching
                if not paper_obj:
                    title = res.get('title')
                    author_name = res.get('authors')
                    paper_qs = Paper.objects.filter(title=title)
                    if author_name:
                        # If author_name is a list, check for any author in the list
                        from django.db.models import Q
                        if isinstance(author_name, list):
                            author_filter = Q()
                            for a in author_name:
                                author_filter |= Q(authors__icontains=a)
                            paper_qs = paper_qs.filter(author_filter)
                        else:
                            paper_qs = paper_qs.filter(authors__icontains=author_name)
                    paper_obj = paper_qs.first()

                results.append({
                    'query': query, 
                    'paper': paper_obj,
                    'snippet': res.get('text', ''),
                    'tags': paper_obj.tags if paper_obj else [],
                    'score': f"{res.get('score', '-')}",
                    'page': res.get('page'),
                })
        except Exception as e:
            # fallback to default search if index not built
            papers = Paper.objects.filter(
                Q(title__icontains=query) | Q(abstract__icontains=query)
            )
            for paper in papers:
                snippet = extract_matching_snippet(paper.abstract, query)
                results.append({
                    'query': query,
                    'paper': paper,
                    'snippet': snippet,
                    'tags': paper.tags,
                })
    else:
        for paper in papers:
            results.append({
                'query': query,
                'paper': paper,
                'snippet': "",
                'tags': paper.tags,
        })
            
    paginator = Paginator(results, 10)  # Show 10 items per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, 'papers/paper_list.html', {
        'results': results,
        'query': query ,
        'page_obj': page_obj})

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
    papers = Paper.objects.all().order_by("-uploaded_at")  
    if request.method == 'POST':
        form = PaperForm(request.POST, request.FILES)
        if form.is_valid():
            paper = form.save(commit=False)
            paper.is_indexed = False  # Initially set to False
            
            # Extract tags from abstract
            tags = extract_tags((paper.title or "") + " " + (paper.abstract or "") + " " + (paper.summary or ""))
            paper.tags = tags
            paper.save()

            # Auto-generate summary and embed for semantic search
            if paper.file:
                try:
                    # --- Auto-summary ---
                    from utils.summarize import extract_text_from_pdf, summarize_text
                    text = extract_text_from_pdf(paper.file.path)
                    print(f"[DEBUG] Extracted text length: {len(text)}")
                    summary = summarize_text(text)
                    print(f"[DEBUG] Summary: {summary}")
                    paper.summary = summary
                    paper.save(update_fields=['summary'])
                except Exception as e:
                    import traceback
                    print(f"[Summary Error] {e}")
                    traceback.print_exc()
                try:
                    # Pass paper.id as paper_id for correct metadata
                    index_paper(paper.file.path, paper.title, paper.authors, paper.id)
                    paper.is_indexed = True  # Set to True after successful indexing
                    paper.save(update_fields=['is_indexed'])
                except Exception as e:
                    print(f"[Embedding Error] {e}")

            return redirect('/papers/upload?status=success')
    else:
        form = PaperForm()
    status = request.GET.get('status')
    return render(request, 'papers/paper_upload.html', {'form': form, 'status': status, 'papers': papers,})


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