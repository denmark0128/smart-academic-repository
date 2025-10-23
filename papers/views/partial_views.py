from django.shortcuts import render
from papers.models import Paper
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from utils.semantic_search import semantic_search, keyword_search, index_paper, get_model
from collections import Counter
from .views import extract_matching_snippet

@login_required
def uploaded_papers_partial(request):
    # Only get papers uploaded by the currently logged-in user
    papers = Paper.objects.filter(uploaded_by=request.user).order_by('-uploaded_at')
    return render(request, 'papers/partials/uploads/uploaded_papers.html', {'papers': papers})

def paper_list_partial(request):
    query = request.GET.get('q')
    author_filter = request.GET.get('author')
    tags = request.GET.getlist('tag')
    college = request.GET.get('college')
    program = request.GET.get('program')
    year = request.GET.get('year')
    view_mode = request.GET.get('view_mode', 'card')

    results = []

    # --- Tag counts ---
    tag_data = Paper.objects.only('tags').values_list('tags', flat=True)
    all_tags = []
    for tlist in tag_data:
        if isinstance(tlist, list):
            all_tags.extend(tlist)
    tag_counts = dict(Counter(all_tags))

    # --- Base queryset (defer heavy fields) ---
    papers = Paper.objects.defer(
        'title_embedding', 'abstract_embedding', 'summary', 'file'
    ).all()

    # --- Apply filters ---
    if college:
        papers = papers.filter(college=college)
    if program:
        papers = papers.filter(program=program)
    if year:
        try:
            papers = papers.filter(year=int(year))
        except (ValueError, TypeError):
            pass
    if tags:
        tag_filters = Q()
        for t in tags:
            tag_filters |= Q(tags__contains=[t])
        papers = papers.filter(tag_filters)

    # --- Active filters ---
    active_filters = []
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
    for t in tags:
        remaining_tags = [x for x in tags if x != t]
        query_dict = request.GET.copy()
        query_dict.setlist('tag', remaining_tags)
        active_filters.append({
            "label": "Tag",
            "value": t,
            "remove_url": query_dict.urlencode()
        })

    # --- Determine saved papers ---
    saved_paper_ids = []
    if request.user.is_authenticated:
        saved_paper_ids = list(request.user.saved_papers.values_list('paper_id', flat=True))

    # --- Searching ---
    try:
        if query:
            # Author filter
            if author_filter:
                papers_by_author = Paper.objects.filter(authors__contains=[author_filter])[:10]
                for paper in papers_by_author:
                    snippet = extract_matching_snippet(
                        paper.abstract or paper.summary or '', query or author_filter
                    )
                    paper.is_saved = paper.id in saved_paper_ids
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
                print('Performing search for query:', query)
                search_results = keyword_search(query, top_k=50)
                if not search_results:
                    print('No keyword search results, falling back to semantic search')
                    search_results = semantic_search(query, top_k=50)

            # Build result objects
            paper_ids = [r.get("paper_id") for r in search_results]
            papers_map = {p.id: p for p in papers.filter(id__in=paper_ids)}
            for r in search_results:
                paper = papers_map.get(r.get("paper_id"))
                if not paper:
                    continue
                paper.is_saved = paper.id in saved_paper_ids
                results.append({
                    "query": query,
                    "paper": paper,
                    "snippet": r.get("text", ""),
                    "tags": paper.tags,
                    "score": f"{r.get('score', 0):.3f}" if r.get('score') is not None else "-",
                    "page": r.get("page"),
                })
        else:
            # No query → just filtered papers
            for paper in papers:
                paper.is_saved = paper.id in saved_paper_ids
                results.append({
                    "query": query,
                    "paper": paper,
                    "snippet": "",
                    "tags": paper.tags,
                    "score": "-",
                    "page": None,
                })

    except Exception as e:
        import traceback
        traceback.print_exc()
        for paper in papers:
            snippet = extract_matching_snippet(paper.abstract or '', query or '')
            paper.is_saved = paper.id in saved_paper_ids
            results.append({
                "query": query,
                "paper": paper,
                "snippet": snippet,
                "tags": paper.tags,
                "score": "-",
                "page": None,
            })

    # --- Pagination ---
    paginator = Paginator(results, 10)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # --- Unique values for filters ---
    colleges = Paper.objects.values_list('college', flat=True).distinct()
    programs = Paper.objects.values_list('program', flat=True).distinct()
    years = Paper.objects.values_list('year', flat=True).distinct()
    years = sorted([y for y in years if y is not None], reverse=True)

    context = {
        "results": page_obj,  # only paginated
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
    }

    return render(request, "papers/partials/paper_list/_paper_list_content.html", context)

@login_required
def saved_papers_partial(request):
    saved = request.user.saved_papers.select_related(
        'paper',
        'paper__uploaded_by' 
    ).order_by('-saved_at')

    return render(request, 'profile/partials/saved_papers_partial.html', {
        'saved_papers': saved
    })
