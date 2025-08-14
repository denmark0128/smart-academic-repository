from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from .models import Paper, SavedPaper, MatchedCitation
from .forms import PaperForm
#from .models import AcademicPaper
from django.http import HttpResponse, JsonResponse
from .utils.nlp import extract_tags
from django.db.models import Q
import re
import os
import fitz
from django.conf import settings
from django.utils.http import urlencode
from utils.semantic_search import semantic_search, keyword_search, index_paper
from utils.metadata_extractor import extract_metadata as extract_metadata_from_pdf
from utils.metadata_extractor import normalize_college, normalize_program
from utils.related import find_related_papers
from django.contrib.auth.decorators import login_required
from collections import Counter
import json


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
                author_name = res.get('authors')  # make sure this is a string like "Cervantes"
                title = res.get('title')
                
                paper_qs = Paper.objects.filter(title=title)
                
                if author_name:
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
    
    # Absolute URL for PDF
    pdf_url = request.build_absolute_uri(paper.file.url)
    viewer_url = f"{settings.STATIC_URL}pdfjs/web/viewer.html?{urlencode({'file': pdf_url})}"
    matched_citations = paper.matched_citations.select_related("matched_paper")
    matched_citation_count = matched_citations.count()
    citations_pointing_here = MatchedCitation.objects.filter(matched_paper=paper).select_related("source_paper")
    citation_count = citations_pointing_here.count()

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
    })


def paper_upload(request):
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
                    index_paper(paper.file.path, paper.title, [a.full_name for a in paper.authors.all()])
                    paper.is_indexed = True  # Set to True after successful indexing
                    paper.save(update_fields=['is_indexed'])
                except Exception as e:
                    print(f"[Embedding Error] {e}")

            return redirect('/papers/upload?status=success')
    else:
        form = PaperForm()
    status = request.GET.get('status')
    return render(request, 'papers/paper_upload.html', {'form': form, 'status': status})


@login_required
def profile_page(request):
    return render(request, 'profile/show.html', {'user': request.user})

@login_required
def save_paper(request, paper_id):
    paper = get_object_or_404(Paper, id=paper_id)
    SavedPaper.objects.get_or_create(user=request.user, paper=paper)
    return redirect(request.META.get('HTTP_REFERER', 'paper_list'))

@login_required
def unsave_paper(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    SavedPaper.objects.filter(user=request.user, paper=paper).delete()
    return JsonResponse({'status': 'unsaved'})

@login_required
def saved_papers_view(request):
    saved = SavedPaper.objects.filter(user=request.user).select_related('paper')
    return render(request, 'papers/saved_papers.html', {'saved_papers': saved})

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

