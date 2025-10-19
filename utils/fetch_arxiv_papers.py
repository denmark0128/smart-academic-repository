import arxiv
from yourapp.models import Paper  # adjust to your actual Django app
from django.utils.text import slugify

def import_arxiv_papers(query="semantic search", max_results=10):
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    for result in search.results():
        title = result.title
        authors = ", ".join([a.name for a in result.authors])
        year = result.updated.year
        abstract = result.summary
        pdf_url = result.pdf_url
        doi = result.doi or ""
        arxiv_id = result.entry_id.split("/")[-1]

        # Avoid duplicates
        if Paper.objects.filter(external_id=arxiv_id, source="arxiv").exists():
            continue

        paper = Paper.objects.create(
            title=title,
            author=authors,
            year=year,
            abstract=abstract,
            pdf_url=pdf_url,
            external_id=arxiv_id,
            source="arxiv",
            slug=slugify(title),
        )

        print(f"✅ Added: {title} ({year})")

# Example usage:
# import_arxiv_papers("semantic search", 5)
