from sentence_transformers import SentenceTransformer
from django.db.models import Q
from papers.models import Paper, PaperChunk

# Load model once globally
model = SentenceTransformer("google/embeddinggemma-300m")


def find_related_papers(paper_title, top_k=5, min_score=0.1):
    """
    Find related papers by comparing embeddings of chunks belonging to the given paper title
    against all other chunks in the database (pgvector).
    """
    paper = Paper.objects.filter(title__iexact=paper_title).first()
    if not paper:
        print(f"No paper found with title: {paper_title}")
        return []

    # Collect all chunks of this paper
    paper_chunks = PaperChunk.objects.filter(paper=paper)
    if not paper_chunks.exists():
        print(f"No chunks found for paper titled '{paper_title}'")
        return []

    # Merge all chunk texts into one representation
    paper_text = " ".join(c.text for c in paper_chunks)
    query_emb = model.encode(paper_text).tolist()

    # Search across all chunks in the DB using pgvector
    matches = (
        PaperChunk.objects
        .exclude(paper=paper)  # skip same paper
        .annotate(distance=PaperChunk.embedding.cosine_distance(query_emb))
        .order_by("distance")[: top_k * 5]  # fetch more for filtering
    )

    related = {}
    for m in matches:
        score = 1 - m.distance  # cosine similarity
        if score < min_score:
            continue
        related_title = m.paper.title if m.paper else "Unknown"
        if related_title not in related or score > related[related_title]['score']:
            related[related_title] = {
                "title": related_title,
                "authors": m.paper.authors if m.paper else [],
                "score": float(score),
            }
        if len(related) >= top_k:
            break

    results = sorted(related.values(), key=lambda x: x["score"], reverse=True)
    print(f"Found {len(results)} related papers.")
    return results


def build_title_index(papers):
    """
    In pgvector you don’t need to build a separate FAISS index.
    This is a no-op kept for API compatibility.
    """
    print("pgvector stores embeddings directly in the DB. No FAISS index needed.")
    return
