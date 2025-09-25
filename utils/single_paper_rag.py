import json
from llama_cpp import Llama
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from django.conf import settings
import os

# ----------------------------
# GLOBAL LOAD (once per server run)
# ----------------------------
BASE_DIR = settings.BASE_DIR
INDEX_FILE = os.path.join(BASE_DIR, "media", "indices", "paragraphs.index")
JSON_FILE = os.path.join(BASE_DIR, "media", "indices", "paragraphs_metadata.json")


# Lazy loading for FAISS index
_faiss_index = None
def get_faiss_index():
    global _faiss_index
    if _faiss_index is None:
        _faiss_index = faiss.read_index(INDEX_FILE)
    return _faiss_index

# Lazy loading for metadata
_chunks_data = None
def get_chunks_data():
    global _chunks_data
    if _chunks_data is None:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            _chunks_data = json.load(f)
    return _chunks_data

# Lazy loading for chunk map
_chunk_map = None
def get_chunk_map():
    global _chunk_map
    if _chunk_map is None:
        chunks_data = get_chunks_data()
        _chunk_map = {i: chunks_data[i] for i in range(len(chunks_data))}
    return _chunk_map

# Lazy loading for embedding model
_embed_model = None
def get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embed_model

# Load LLM
"""
llm = Llama.from_pretrained(
    repo_id="unsloth/gemma-3-1b-it-GGUF",
    filename="gemma-3-1b-it-BF16.gguf",
    n_ctx=32768,
)
"""

# ----------------------------
# RAG query function
# ----------------------------
def query_rag(user_query, top_k=3):
    # Embed query
    embed_model = get_embed_model()
    query_vec = embed_model.encode([user_query])

    # Retrieve top-k chunks
    index = get_faiss_index()
    chunk_map = get_chunk_map()
    D, I = index.search(np.array(query_vec), top_k)
    retrieved_chunks = [chunk_map[i] for i in I[0]]

    # Build context string
    context_str = ""
    for c in retrieved_chunks:
        context_str += f"[{c['title']} - page {c['page']}]\n{c['text']}\n\n"

    # Build prompt
    prompt = f"""
You are an expert assistant. Answer the user's question using ONLY the following context.
Include references to the paper title and page number whenever relevant.

Context:
{context_str}

User query: "{user_query}"
"""

    # Generate answer
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    
    return response["choices"][0]["message"]["content"]
