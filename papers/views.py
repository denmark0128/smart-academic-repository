from django.shortcuts import render, get_object_or_404, redirect
from .models import Paper, SavedPaper
from .forms import PaperForm
#from .models import AcademicPaper
from django.http import HttpResponse, JsonResponse
from .utils.nlp import extract_tags
from django.db.models import Q
import re
from django.conf import settings
from django.utils.http import urlencode
from utils.semantic_search import semantic_search, keyword_search
from django.contrib.auth.decorators import login_required


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
                results.append({
                    'query': query, 
                    'paper': Paper.objects.filter(title=res['title'], author=res['author']).first(),
                    'snippet': res.get('text', ''),
                    'tags': [],
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
                tags = extract_tags(paper.abstract or "")
                results.append({
                    'query': query,
                    'paper': paper,
                    'snippet': snippet,
                    'tags': tags,
                })
    else:
        for paper in papers:
            tags = extract_tags(paper.abstract or "")
            results.append({
                'query': query,
                'paper': paper,
                'snippet': "",
                'tags': tags,
        })

    return render(request, 'papers/paper_list.html', {'results': results, 'query': query})

def paper_detail(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    tags = extract_tags(paper.abstract or paper.content or "")
    
    # Absolute URL for PDF
    pdf_url = request.build_absolute_uri(paper.file.url)
    viewer_url = f"{settings.STATIC_URL}pdfjs/web/viewer.html?{urlencode({'file': pdf_url})}"

    return render(request, 'papers/paper_detail.html', {
        'paper': paper,
        'tags': tags,
        'viewer_url': viewer_url,
    })


def paper_upload(request):
    if request.method == 'POST':
        form = PaperForm(request.POST, request.FILES)
        if form.is_valid():
            paper = form.save(commit=False)
            # Extract tags from abstract and save
            tags = extract_tags(paper.abstract or "")
            paper.tags = tags
            paper.save()
            return redirect('paper_list')
    else:
        form = PaperForm()
    return render(request, 'papers/paper_upload.html', {'form': form})

@login_required
def profile_page(request):
    return render(request, 'profile/show.html', {'user': request.user})

@login_required
def save_paper(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    SavedPaper.objects.get_or_create(user=request.user, paper=paper)
    return JsonResponse({'status': 'saved'})

@login_required
def unsave_paper(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    SavedPaper.objects.filter(user=request.user, paper=paper).delete()
    return JsonResponse({'status': 'unsaved'})

@login_required
def saved_papers_list(request):
    saved_papers = SavedPaper.objects.filter(user=request.user).select_related('paper')
    return render(request, 'profile/saved_papers.html', {'saved_papers': saved_papers})

def pdf_viewer(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    return render(request, 'papers/pdf_reader.html', {
        'pdf_url': paper.pdf_file.url  # e.g., "/media/papers/sample.pdf"
    })