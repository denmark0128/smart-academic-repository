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
from staff.utils import get_search_settings 

# -------------------------------
# Settings
# -------------------------------

_model = None
_embedding_model_name_loaded = None  # Track the name of the loaded model

def get_model():
    """
    Load the SentenceTransformer model specified in SearchSettings.
    Caches the model globally. If the setting changes, it reloads.
    """
    global _model, _embedding_model_name_loaded
    
    # Get the configured model name from settings
    settings = get_search_settings()
    
    # ⬇️ READ THE RENAMED FIELD ⬇️
    configured_model_name = settings.embedding_model_name 
    
    # If the model isn't loaded OR the name changed in settings
    if _model is None or _embedding_model_name_loaded != configured_model_name:
        print(f"🔄 Loading/Reloading embedding model: {configured_model_name}...")
        try:
            _model = SentenceTransformer(configured_model_name)
            _embedding_model_name_loaded = configured_model_name  # Store its name
            print("✅ Embedding model loaded.")
        except Exception as e:
            print(f"❌ Failed to load embedding model '{configured_model_name}': {e}")
            _model = None  
            _embedding_model_name_loaded = None
            return None
            
    return _model


# -------------------------------
# PDF extraction & chunking
# -------------------------------
from langchain.text_splitter import RecursiveCharacterTextSplitter


from langchain.text_splitter import RecursiveCharacterTextSplitter
import fitz
import re

def extract_and_chunk(pdf_path, chunk_size=None, chunk_overlap=None):
    """
    Extracts text from PDF and chunks recursively, ignoring appendices after configurable chars.
    """
    # ✅ Get configurable settings
    search_settings = get_search_settings()
    if chunk_size is None:
        chunk_size = search_settings.chunk_size
    if chunk_overlap is None:
        chunk_overlap = search_settings.chunk_overlap
    
    print(f"[CHUNKING] Using settings from database:")
    print(f"  - chunk_size: {chunk_size}")
    print(f"  - chunk_overlap: {chunk_overlap}")
    print(f"  - appendix_cutoff: {search_settings.appendix_cutoff}")

    doc = fitz.open(pdf_path)
    full_text = ""
    page_map = []  # Track which page each character belongs to
    
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("text")
        
        # ✅ Use configurable appendix cutoff
        if len(full_text) > search_settings.appendix_cutoff:
            if re.search(r'(^|\n)\s*(APPENDIX|APPENDICES)', text, re.IGNORECASE | re.MULTILINE):
                # Stop here, ignore rest
                break
        
        full_text += text
        page_map.extend([page_num] * len(text))
    
    doc.close()
    
    # Recursive chunking with LangChain
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    chunks = text_splitter.split_text(full_text)
    
    # Add metadata
    result = []
    char_position = 0
    for i, chunk in enumerate(chunks):
        # Find approximate page for this chunk
        chunk_start = full_text.find(chunk, char_position)
        page_num = page_map[chunk_start] if chunk_start < len(page_map) else page_map[-1]
        
        result.append({
            "text": chunk,
            "chunk_id": i,
            "page": page_num
        })
        char_position = chunk_start + len(chunk)
    
    return result
    
    doc.close()
    
    # Recursive chunking with LangChain
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    
    chunks = text_splitter.split_text(full_text)
    
    # Add metadata
    result = []
    char_position = 0
    for i, chunk in enumerate(chunks):
        # Find approximate page for this chunk
        chunk_start = full_text.find(chunk, char_position)
        page_num = page_map[chunk_start] if chunk_start < len(page_map) else page_map[-1]
        
        result.append({
            "text": chunk,
            "chunk_id": i,
            "page": page_num
        })
        char_position = chunk_start + len(chunk)
    
    return result


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

def semantic_search(query, top_k=None, min_score=None, bm25_weight=None, vector_weight=None):
    # ✅ Get configurable settings
    search_settings = get_search_settings()
    if top_k is None:
        top_k = search_settings.top_k_results
    if min_score is None:
        min_score = search_settings.min_similarity_score
    if bm25_weight is None:
        bm25_weight = search_settings.bm25_weight
    if vector_weight is None:
        vector_weight = search_settings.vector_weight
    
    # ✅ Print to verify values
    print(f"[SEARCH] Using settings from database:")
    print(f"  - top_k: {top_k}")
    print(f"  - min_score: {min_score}")
    print(f"  - bm25_weight: {bm25_weight}")
    print(f"  - vector_weight: {vector_weight}")
    print(f"  - hybrid_search_multiplier: {search_settings.hybrid_search_multiplier}")
    print(f"  - hybrid_search_min_results: {search_settings.hybrid_search_min_results}")

    model = get_model()
    query_emb = model.encode([query], convert_to_numpy=True)[0]
    query_emb_list = query_emb.tolist()

    search_vector = SearchVector('text', weight='A')
    search_query = SearchQuery(query)
    
    # ✅ Use configurable initial limit
    initial_limit = max(
        search_settings.hybrid_search_min_results,
        top_k * search_settings.hybrid_search_multiplier
    )
    
    # Single query with both BM25 and vector distance
    results = list(  # ✅ Evaluate once here
        PaperChunk.objects
        .select_related('paper')
        .annotate(
            bm25=SearchRank(search_vector, search_query),
            distance=CosineDistance("embedding", query_emb_list)
        )
        .filter(bm25__gt=0)
        .order_by('-bm25')[:initial_limit]  # ✅ Use configurable limit
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
        
        bm25_norm = norm(res.bm25, bm25_scores)
        vector_norm = norm(vector_score, vector_scores)
        hybrid_score = bm25_weight * bm25_norm + vector_weight * vector_norm
        
        # ✅ Filter by hybrid_score instead
        if hybrid_score < min_score:
            continue
            
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
def keyword_search(query, top_k=None):
    """
    Simple keyword search across chunks.
    """
    if not query:
        return []

    # ✅ Get configurable settings
    search_settings = get_search_settings()
    if top_k is None:
        top_k = search_settings.top_k_results

    # ✅ Use configurable max_chunks_scan
    qs = (
        PaperChunk.objects
        .filter(text__icontains=query)
        .select_related("paper")[:search_settings.max_chunks_scan]
    )

    print(f"[KEYWORD SEARCH] Using settings from database:")
    print(f"  - top_k: {top_k}")
    print(f"  - max_chunks_scan: {search_settings.max_chunks_scan}")

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
