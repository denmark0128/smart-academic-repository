from django.shortcuts import render, get_object_or_404, redirect
from .models import Paper
from .forms import PaperForm
#from .models import AcademicPaper
from django.http import HttpResponse
from .utils.nlp import extract_tags
from django.db.models import Q
import re


def home(request):
    return render(request, 'home.html', {'name': 'John'})


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
        papers = Paper.objects.filter(
            Q(title__icontains=query) | Q(abstract__icontains=query)
        )
        for paper in papers:
            snippet = extract_matching_snippet(paper.abstract, query)
            tags = extract_tags(paper.abstract or "")  # Extract tags from abstract
            results.append({
                'paper': paper,
                'snippet': snippet,
                'tags': tags,
            })
    else:
        for paper in papers:
            tags = extract_tags(paper.abstract or "")
            results.append({
                'paper': paper,
                'snippet': "",
                'tags': tags,
        })

    return render(request, 'papers/paper_list.html', {'results': results, 'query': query})

def paper_detail(request, pk):
    paper = get_object_or_404(Paper, pk=pk)
    tags = extract_tags(paper.abstract or paper.content or "")  # Adjust field as needed

    return render(request, 'papers/paper_detail.html', {
        'paper': paper,
        'tags': tags,
    })

def paper_upload(request):
    if request.method == 'POST':
        form = PaperForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return redirect('paper_list')
    else:
        form = PaperForm()
    return render(request, 'papers/paper_upload.html', {'form': form})
