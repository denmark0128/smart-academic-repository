import re
import fitz  # PyMuPDF
import numpy as np
from sentence_transformers import SentenceTransformer
from papers.models import Paper, PaperChunk
from django.db.models import Func, FloatField, Value
from pgvector.django import CosineDistance

# -------------------------------
# Settings
# -------------------------------
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_model = None


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBED_MODEL)
    return _model


# -------------------------------
# PDF extraction & chunking
# -------------------------------
def extract_and_chunk(pdf_path, min_size=100, max_size=500):
    """
    Extracts text from a PDF and chunks into paragraphs of reasonable size.
    """
    doc = fitz.open(pdf_path)
    all_chunks = []

    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text").replace("\r", "").strip()
        # Split into paragraphs by double newlines
        raw_paragraphs = re.split(r"\n\s*\n", text)
        paragraphs = [
            re.sub(r"\s+", " ", p).strip()
            for p in raw_paragraphs if p.strip()
        ]

        buffer = ""
        for para in paragraphs:
            if len(buffer.split()) + len(para.split()) < min_size:
                buffer += " " + para
            else:
                if buffer:
                    all_chunks.append({"text": buffer.strip(), "page": page_num})
                    buffer = ""
                while len(para.split()) > max_size:
                    split_point = para[:max_size].rfind(".")
                    if split_point == -1:
                        split_point = max_size
                    all_chunks.append({"text": para[:split_point+1].strip(), "page": page_num})
                    para = para[split_point+1:]
                buffer = para
        if buffer:
            all_chunks.append({"text": buffer.strip(), "page": page_num})

    return [
        {**chunk, "chunk_id": i} for i, chunk in enumerate(all_chunks)
    ]


# -------------------------------
# Indexing
# -------------------------------
def index_paper(paper: Paper):
    """
    Extract, chunk, embed, and save PaperChunks into DB for a Paper.
    """
    chunks = extract_and_chunk(paper.file.path)
    model = get_model()
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, convert_to_numpy=True)

    objs = []
    for i, chunk in enumerate(chunks):
        objs.append(
            PaperChunk(
                paper=paper,
                title=paper.title,
                authors=paper.authors,
                page=chunk["page"],
                chunk_id=i,
                text=chunk["text"],
                embedding=embeddings[i],  # pgvector accepts np.ndarray
            )
        )

    PaperChunk.objects.bulk_create(objs)
    paper.is_indexed = True
    paper.save()


# -------------------------------
# Semantic Search
# -------------------------------


from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

def semantic_search(query, top_k=5, min_score=0.25, bm25_weight=0.5, vector_weight=0.5):
    """
    Hybrid BM25 (full-text) + vector similarity search.
    1. Use BM25 to get top candidates.
    2. Re-rank with vector similarity.
    3. Combine scores for final ranking.
    """
    model = get_model()
    query_emb = model.encode([query], convert_to_numpy=True)[0]
    query_emb_list = query_emb.tolist()

    # Step 1: BM25 (full-text) search for candidates
    search_vector = SearchVector('text', weight='A')
    search_query = SearchQuery(query)
    bm25_qs = (
        PaperChunk.objects
        .annotate(bm25=SearchRank(search_vector, search_query))
        .filter(bm25__gt=0)
        .order_by('-bm25')[:max(20, top_k*2)]  # get more for re-ranking
    )

    # Step 2: For each candidate, compute vector similarity
    # (pgvector CosineDistance: similarity = 1 - distance)
    candidates = list(bm25_qs)
    if not candidates:
        # fallback to pure vector search if no BM25 hits
        results = (
            PaperChunk.objects
            .annotate(distance=CosineDistance("embedding", query_emb_list))
            .order_by("distance")[:top_k]
        )
        output = []
        for res in results:
            similarity = 1 - res.distance
            if similarity < min_score:
                continue
            output.append({
                "paper_id": res.paper.id,
                "title": res.paper.title,
                "authors": res.paper.authors,
                "page": res.page,
                "text": highlight_query(res.text, query),
                "score": round(similarity, 4),
            })
        return output

    # Get vector similarities for candidates
    # (fetch all candidate ids, then annotate with vector distance)
    candidate_ids = [c.id for c in candidates]
    vector_qs = (
        PaperChunk.objects
        .filter(id__in=candidate_ids)
        .annotate(distance=CosineDistance("embedding", query_emb_list))
    )
    # Map id to vector similarity
    id_to_vector = {c.id: 1 - c.distance for c in vector_qs}
    # Map id to bm25
    id_to_bm25 = {c.id: c.bm25 for c in candidates}

    # Normalize scores
    bm25_scores = list(id_to_bm25.values())
    vector_scores = list(id_to_vector.values())
    def norm(x, scores):
        if not scores or max(scores) == min(scores):
            return 1.0 if scores and x == max(scores) else 0.0
        return (x - min(scores)) / (max(scores) - min(scores))

    # Combine scores
    combined = []
    for cid in candidate_ids:
        bm25_norm = norm(id_to_bm25[cid], bm25_scores)
        vector_norm = norm(id_to_vector.get(cid, 0), vector_scores)
        hybrid_score = bm25_weight * bm25_norm + vector_weight * vector_norm
        combined.append((cid, hybrid_score, id_to_bm25[cid], id_to_vector.get(cid, 0)))

    # Sort by hybrid score
    combined.sort(key=lambda x: x[1], reverse=True)

    # Build output: only return unique papers (best chunk per paper)
    paper_best = {}
    for cid, hybrid_score, bm25_score, vector_score in combined:
        chunk = next((c for c in candidates if c.id == cid), None)
        if not chunk:
            continue
        if vector_score < min_score:
            continue
        pid = chunk.paper.id
        # If this paper is not yet added or this chunk has a better score, update
        if pid not in paper_best or hybrid_score > paper_best[pid]["score"]:
            paper_best[pid] = {
                "paper_id": chunk.paper.id,
                "title": chunk.paper.title,
                "authors": chunk.paper.authors,
                "page": chunk.page,
                "text": highlight_query(chunk.text, query),
                "score": round(hybrid_score, 4),
                "bm25": round(bm25_score, 4),
                "vector": round(vector_score, 4),
            }
    # Return top_k unique papers by score
    output = sorted(paper_best.values(), key=lambda x: x["score"], reverse=True)[:top_k]
    return output


# -------------------------------
# Keyword Search
# -------------------------------
def keyword_search(query, top_k=5):
    """
    Simple keyword search across chunks.
    """
    qs = (
        PaperChunk.objects
        .filter(text__icontains=query)
        .select_related("paper")[:top_k]
    )

    return [
        {
            "paper_id": c.paper.id,
            "title": c.paper.title,
            "authors": c.paper.authors,
            "page": c.page,
            "text": highlight_query(c.text, query),
            "score": None,
            "match_type": "keyword",
        }
        for c in qs
    ]


# -------------------------------
# Helpers
# -------------------------------
def highlight_query(text, query):
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    return pattern.sub(r"<mark>\g<0></mark>", text)
