import os
import json
import fitz  # PyMuPDF
import faiss
import re
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer, util

INDEX_PATH = os.path.join('media', 'indices', 'paragraphs.index')
META_PATH = os.path.join('media', 'indices', 'paragraphs_metadata.json')

EMBED_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'  # or 'allenai-specter'

_model_instance = None
def get_model():
    global _model_instance
    if _model_instance is None:
        _model_instance = SentenceTransformer(EMBED_MODEL)
    return _model_instance


def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = []
    for page_num, page in enumerate(doc):
        text.append(page.get_text())
    return text  # list of page text

def is_reference_heading(line):
    return re.match(r"^\s*(references|bibliography|works cited)\s*$", line.strip(), re.IGNORECASE)

def remove_references(pages):
    clean_pages = []
    found_references = False
    for page_text in pages:
        if found_references:
            break
        lines = page_text.split("\n")
        filtered_lines = []
        for line in lines:
            if is_reference_heading(line):
                found_references = True
                break
            filtered_lines.append(line)
        clean_pages.append("\n".join(filtered_lines))
    return clean_pages

def merge_small_by_similarity(paragraphs, min_tokens=25, max_tokens=500, similarity_threshold=0.3):
    merged = []
    buffer = ""
    buffer_emb = None
    model = get_model()
    for para in paragraphs:
        if not para.strip():
            continue
        emb = model.encode(para, convert_to_tensor=True)
        if not buffer:
            buffer = para
            buffer_emb = emb
            continue
        score = util.cos_sim(buffer_emb, emb).item()
        if score >= similarity_threshold and len(buffer.split()) + len(para.split()) <= max_tokens:
            buffer += " " + para
            buffer_emb = model.encode(buffer, convert_to_tensor=True)
        else:
            merged.append(buffer.strip())
            buffer = para
            buffer_emb = emb
    if buffer:
        merged.append(buffer.strip())
    return merged


def extract_and_chunk(pdf_path, min_size=100, max_size=500):
    doc = fitz.open(pdf_path)
    # Step 1: get page texts
    page_texts = [page.get_text("text").replace("\r","").strip() for page in doc]

    # Step 2: process each page separately to preserve page numbers
    all_chunks = []
    for page_num, text in enumerate(page_texts, start=1):
        # Merge paragraphs within the page
        raw_paragraphs = re.split(r"\n\s*\n", text)
        paragraphs = [re.sub(r"\s+", " ", re.sub(r"\n(?!\n)", " ", p)).strip() for p in raw_paragraphs if p.strip()]

        # Merge short headers
        merged_paragraphs = []
        skip_next = False
        for i, para in enumerate(paragraphs):
            if skip_next:
                skip_next = False
                continue
            if len(para.split()) <= 3 and i + 1 < len(paragraphs):
                merged_paragraphs.append(para + ": " + paragraphs[i+1])
                skip_next = True
            else:
                merged_paragraphs.append(para)

        # Semantic merge within the page
        semantically_merged = merge_small_by_similarity(merged_paragraphs, min_tokens=25, max_tokens=max_size, similarity_threshold=0.7)

        # Final chunk by size, preserving page number
        buffer = ""
        for para in semantically_merged:
            if len(buffer) + len(para) < min_size:
                buffer += " " + para
            else:
                if buffer:
                    all_chunks.append({'text': buffer.strip(), 'page': page_num})
                    buffer = ""
                while len(para) > max_size:
                    split_point = para[:max_size].rfind(".")
                    if split_point == -1:
                        split_point = max_size
                    all_chunks.append({'text': para[:split_point+1].strip(), 'page': page_num})
                    para = para[split_point+1:]
                buffer = para
        if buffer:
            all_chunks.append({'text': buffer.strip(), 'page': page_num})
    return all_chunks

###
def chunk_text(pages, chunk_size=2000, chunk_overlap=200):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks = []
    for page_num, page_text in enumerate(pages):
        for chunk in splitter.split_text(page_text):
            chunks.append({'text': chunk, 'page': page_num + 1})
    return chunks
###


def embed_chunks(chunks):
    texts = [c['text'] for c in chunks]
    model = get_model()
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    return embeddings


def build_faiss_index(embeddings):
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)
    return index


def save_index(index, path=INDEX_PATH):
    faiss.write_index(index, path)

def save_metadata(metadata, path=META_PATH):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

def load_index(path=INDEX_PATH):
    return faiss.read_index(path)

def load_metadata(path=META_PATH):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def index_paper(pdf_path, title, authors, paper_id=None):
    chunks = extract_and_chunk(pdf_path)
    embeddings = embed_chunks(chunks)

    # Try to load existing index and metadata
    try:
        index = load_index()
        metadata = load_metadata()
    except Exception:
        index = None
        metadata = []

    if index is not None and len(metadata) > 0:
        # Append to existing index and metadata
        faiss.normalize_L2(embeddings)
        index.add(embeddings)
        save_index(index)
        offset = len(metadata)
    else:
        # Create new index and metadata
        index = build_faiss_index(embeddings)
        save_index(index)
        offset = 0
        metadata = []

    # Add new metadata with correct chunk_id
    for i, chunk in enumerate(chunks):
        metadata.append({
            'paper_id': paper_id,
            'title': title.strip(),
            'page': chunk['page'],
            'chunk_id': offset + i,
            'text': chunk['text'],
        })
    save_metadata(metadata)


def build_full_index(papers):
    """
    Build a single FAISS index and metadata for all papers.
    papers: list of dicts with keys: pdf_path, title, author
    """
    all_chunks = []
    all_metadata = []
    for paper in papers:
        chunks = extract_and_chunk(paper['pdf_path'])
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk['text'])
            all_metadata.append({
                'title': paper['title'],
                'authors': paper['authors'],  
                'page': chunk['page'],
                'chunk_id': len(all_metadata),
                'text': chunk['text'],
            })
    if not all_chunks:
        return
    model = get_model()
    embeddings = model.encode(all_chunks, show_progress_bar=True, convert_to_numpy=True)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)
    save_index(index)
    save_metadata(all_metadata)


def highlight_query(text, query):
    import re
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    return pattern.sub(r'<mark>\g<0></mark>', text)


def semantic_search(query, top_k=5, min_score=0.25):
    index = load_index()
    metadata = load_metadata()
    model = get_model()
    query_emb = model.encode([query], convert_to_numpy=True)
    faiss.normalize_L2(query_emb)
    D, I = index.search(query_emb, top_k * 10)  # Search more to allow filtering
    results = []
    seen_titles = {}
    for score, idx in zip(D[0], I[0]):
        if idx < len(metadata) and score >= min_score:
            meta = metadata[idx].copy()
            title = meta.get('title', '')
            if title not in seen_titles or score > seen_titles[title]['score']:
                meta['score'] = float(score)
                meta['text'] = highlight_query(meta['text'], query)
                seen_titles[title] = meta
        if len(seen_titles) >= top_k:
            break
    results = list(seen_titles.values())
    # Optionally, sort by score descending
    results.sort(key=lambda x: x['score'], reverse=True)
    return results

def keyword_search(query, top_k=5):
    """
    Simple case-insensitive keyword search across all fields (text, title, author).
    Returns up to top_k unique papers (highest match per title).
    """
    metadata = load_metadata()
    query_lower = query.lower()
    seen_titles = {}
    for meta in metadata:
        authors = meta.get('authors', [])
        if isinstance(authors, list):
            author_str = ' '.join(authors)
        else:
            author_str = str(authors)
        haystack = f"{meta.get('text','')} {meta.get('title','')} {author_str}".lower()
        if query_lower in haystack:
            title = meta.get('title', '')
            if title not in seen_titles:
                meta_copy = meta.copy()
                meta_copy['match_type'] = 'keyword'
                seen_titles[title] = meta_copy
            if len(seen_titles) >= top_k:
                break
    return list(seen_titles.values())
