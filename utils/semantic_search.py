import re
import os
import fitz  # PyMuPDF
import numpy as np
from sentence_transformers import SentenceTransformer
from papers.models import Paper, PaperChunk
from django.db.models import Func, FloatField, Value
from pgvector.django import CosineDistance
from utils.html_chunker import process_html_to_chunks
from django.conf import settings

# -------------------------------
# Settings
# -------------------------------
EMBED_MODEL = "google/embeddinggemma-300m"
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
    Supports both PDF (via PyMuPDF) and CHM (via merged.html).
    """
    model = get_model()
    objs = []

    # Detect file type
    ext = os.path.splitext(paper.file.name)[1].lower()

    if ext == ".pdf":
        # Normal PDF embedding flow
        chunks = extract_and_chunk(paper.file.path)

    elif paper.merged_html:
        # ✅ Make sure merged_html exists and is accessible
        merged_html_path = os.path.join(settings.MEDIA_ROOT, paper.merged_html.name)
        if os.path.exists(merged_html_path):
            print(f"[+] Using merged.html for {paper.title}")
            chunks = process_html_to_chunks(merged_html_path, f"{paper.title}_chunks.json")
        else:
            print(f"[!] merged.html not found for {paper.title} → {merged_html_path}")
            return

    else:
        print(f"[!] No valid file found for {paper.title}")
        return

    # --- Embed and save ---
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, convert_to_numpy=True)

    for i, chunk in enumerate(chunks):
        objs.append(
            PaperChunk(
                paper=paper,
                title=paper.title,
                authors=paper.authors,
                page=chunk.get("page", 0),
                chunk_id=i,
                text=chunk["text"],
                embedding=embeddings[i],
            )
        )

    PaperChunk.objects.bulk_create(objs)
    paper.is_indexed = True
    paper.save()
    print(f"[+] Indexed {len(chunks)} chunks for {paper.title}")


# -------------------------------
# Semantic Search
# -------------------------------


from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

def semantic_search(query, top_k=5, min_score=0.25, bm25_weight=0.5, vector_weight=0.5):
    model = get_model()
    query_emb = model.encode([query], convert_to_numpy=True)[0]
    query_emb_list = query_emb.tolist()

    search_vector = SearchVector('text', weight='A')
    search_query = SearchQuery(query)
    
    # Single query with both BM25 and vector distance
    results = list(  # ✅ Evaluate once here
        PaperChunk.objects
        .select_related('paper')
        .annotate(
            bm25=SearchRank(search_vector, search_query),
            distance=CosineDistance("embedding", query_emb_list)
        )
        .filter(bm25__gt=0)
        .order_by('-bm25')[:max(20, top_k*2)]
    )
    
    if not results:
        # Fallback to pure vector search
        results = (
            PaperChunk.objects
            .select_related('paper')
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
    
    # Calculate hybrid scores in Python (already have both scores from annotation)
    bm25_scores = [r.bm25 for r in results]
    vector_scores = [1 - r.distance for r in results]
    
    def norm(x, scores):
        if not scores or max(scores) == min(scores):
            return 1.0 if scores and x == max(scores) else 0.0
        return (x - min(scores)) / (max(scores) - min(scores))
    
    paper_best = {}
    for res in results:
        vector_score = 1 - res.distance
        if vector_score < min_score:
            continue
            
        bm25_norm = norm(res.bm25, bm25_scores)
        vector_norm = norm(vector_score, vector_scores)
        hybrid_score = bm25_weight * bm25_norm + vector_weight * vector_norm
        
        pid = res.paper.id
        if pid not in paper_best or hybrid_score > paper_best[pid]["score"]:
            paper_best[pid] = {
                "paper_id": pid,
                "title": res.paper.title,
                "authors": res.paper.authors,
                "page": res.page,
                "text": highlight_query(res.text, query),
                "score": round(hybrid_score, 4),
            }
    
    return sorted(paper_best.values(), key=lambda x: x["score"], reverse=True)[:top_k]


# -------------------------------
# Keyword Search
# -------------------------------
def keyword_search(query, top_k=5):
    """
    Simple keyword search across chunks.
    """
    if not query:
        return []

    # Fetch candidate chunks that contain the query (case-insensitive)
    # limit the number of chunks scanned for performance
    qs = (
        PaperChunk.objects
        .filter(text__icontains=query)
        .select_related("paper")[:2000]
    )

    # Aggregate occurrences by paper
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    per_paper = {}
    for c in qs:
        text = c.text or ""
        count = len(pattern.findall(text))
        if count == 0:
            continue
        pid = c.paper.id
        if pid not in per_paper:
            per_paper[pid] = {
                "paper_id": pid,
                "title": c.paper.title,
                "authors": c.paper.authors,
                "count": 0,
                "page": c.page,
                "snippet": "",
            }
        per_paper[pid]["count"] += count
        # store the first matching snippet (highlighted)
        if not per_paper[pid]["snippet"]:
            per_paper[pid]["snippet"] = highlight_query(text, query)

    # Convert to list and sort by occurrence count
    results = sorted(per_paper.values(), key=lambda x: x["count"], reverse=True)

    output = []
    for r in results[:top_k]:
        output.append({
            "paper_id": r["paper_id"],
            "title": r["title"],
            "authors": r["authors"],
            "page": r.get("page"),
            "text": r.get("snippet", ""),
            # use score to communicate number of occurrences (as float for compatibility)
            "score": float(r["count"]),
            "match_type": "keyword",
        })

    return output


# -------------------------------
# Helpers
# -------------------------------
def highlight_query(text, query):
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    return pattern.sub(r"<mark>\g<0></mark>", text)
