import os
import json
import fitz  # PyMuPDF
import faiss
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

INDEX_PATH = os.path.join('media', 'indices', 'paragraphs.index')
META_PATH = os.path.join('media', 'indices', 'paragraphs_metadata.json')
EMBED_MODEL = 'all-MiniLM-L6-v2'  # or 'allenai-specter'

model = SentenceTransformer(EMBED_MODEL)


def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = []
    for page_num, page in enumerate(doc):
        text.append(page.get_text())
    return text  # list of page texts


def chunk_text(pages, chunk_size=2000, chunk_overlap=200):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    chunks = []
    for page_num, page_text in enumerate(pages):
        for chunk in splitter.split_text(page_text):
            chunks.append({'text': chunk, 'page': page_num + 1})
    return chunks


def embed_chunks(chunks):
    texts = [c['text'] for c in chunks]
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


def index_paper(pdf_path, title, author):
    pages = extract_text_from_pdf(pdf_path)
    chunks = chunk_text(pages)
    embeddings = embed_chunks(chunks)
    index = build_faiss_index(embeddings)
    save_index(index)
    # Add metadata
    metadata = []
    for i, chunk in enumerate(chunks):
        metadata.append({
            'title': title,
            'author': author,
            'page': chunk['page'],
            'chunk_id': i,
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
        pages = extract_text_from_pdf(paper['pdf_path'])
        chunks = chunk_text(pages)
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk['text'])
            all_metadata.append({
                'title': paper['title'],
                'author': paper['author'],
                'page': chunk['page'],
                'chunk_id': len(all_metadata),
                'text': chunk['text'],
            })
    if not all_chunks:
        return
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
    query_emb = model.encode([query], convert_to_numpy=True)
    faiss.normalize_L2(query_emb)
    D, I = index.search(query_emb, top_k)
    results = []
    for score, idx in zip(D[0], I[0]):
        if idx < len(metadata) and score >= min_score:
            meta = metadata[idx].copy()
            meta['score'] = float(score)
            meta['text'] = highlight_query(meta['text'], query)
            results.append(meta)
    return results
