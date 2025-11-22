from django.shortcuts import render
from django.db.models import Q
from papers.models import Paper, COLLEGE_CHOICES, PROGRAM_CHOICES
from django.contrib.auth.decorators import login_required

@login_required
def paper_library(request):
    # Get filter parameters
    selected_college = request.GET.get('college', '')
    selected_program = request.GET.get('program', '')
    selected_tag = request.GET.get('tag', '')

    # Base queryset
    papers = Paper.objects.all()

    # Apply filters
    if selected_college:
        papers = papers.filter(college=selected_college)
    if selected_program:
        papers = papers.filter(program=selected_program)
    if selected_tag:
        papers = papers.filter(tags__contains=[selected_tag])

    # Get all unique tags
    all_tags = set()
    for paper in Paper.objects.all():
        all_tags.update(paper.tags)
    all_tags = sorted(list(all_tags))

    # Organize papers by college
    college_papers = {}
    for college_code, _ in COLLEGE_CHOICES:
        college_papers[college_code] = papers.filter(college=college_code)

    context = {
        'colleges': COLLEGE_CHOICES,
        'programs': PROGRAM_CHOICES,
        'all_tags': all_tags,
        'college_papers': college_papers,
        'selected_college': selected_college,
        'selected_program': selected_program,
        'selected_tag': selected_tag,
    }

    return render(request, 'papers/paper_library.html', context)