# utils/nlp.py
import re
from spacy.lang.en.stop_words import STOP_WORDS
from sentence_transformers import util
import torch
import json
from .semantic_search import get_model
from django.core.cache import cache
from papers.models import Tag
import numpy as np
from staff.utils import get_search_settings  # ✅ Add this import

_embedding_model = None  # <-- Renamed

def get_embedding_model():   # <-- Renamed
    """
    Get the configured embedding model from semantic_search utility.
    Caches it locally.
    """
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = get_model()  # returns the SentenceTransformer instance
    return _embedding_model

# ... keep all your existing constants and functions ...

# utils/nlp.py

# ... (all your other imports) ...

def extract_tags(text=None, doc_emb=None, top_n=None, min_score=None):  
    """
    Extract relevant tags from text OR a pre-computed embedding.
    Provide EITHER 'text' (to be encoded) OR 'doc_emb' (pre-encoded).
    """
    search_settings = get_search_settings()
    if top_n is None:
        top_n = search_settings.tag_extraction_top_n
    if min_score is None:
        min_score = search_settings.tag_extraction_min_score
    
    print(f"top n: {top_n}")
    print(f"min_score: {min_score}")
    # ... (Your cache loading code is all correct) ...
    # (snip) ...
    cache_key = 'active_tags_with_embeddings'
    cached_data = cache.get(cache_key)
    
    if cached_data is None:
        print("[extract_tags] Cache miss - loading tags from database")
        tags_qs = Tag.objects.filter(is_active=True, embedding__isnull=False).only('name', 'description', 'embedding')
        
        candidates = []
        descriptions = []
        embeddings = []
        
        for tag in tags_qs:
            candidates.append(tag.name)
            descriptions.append(tag.description or tag.name)
            embeddings.append(tag.embedding)
        
        if not candidates:
            print("[extract_tags] No active tags with embeddings found")
            return []
        
        cached_data = {
            'candidates': candidates,
            'descriptions': descriptions,
            'embeddings': embeddings
        }
        cache.set(cache_key, cached_data, search_settings.tag_cache_timeout)
        print(f"[extract_tags] Cached {len(candidates)} tags with embeddings")
    else:
        print(f"[extract_tags] Cache hit - using {len(cached_data['candidates'])} cached tags")
    
    candidates = cached_data['candidates']
    descriptions = cached_data['descriptions']
    embeddings = cached_data['embeddings']
    
    if not candidates:
        return []
    
    # This block is now your single source of truth for doc_emb
    if doc_emb is None:
        if not text or not text.strip():
            print("[extract_tags] No text or embedding provided.")
            return []
        
        print("[extract_tags] Encoding provided text...")
        model = get_embedding_model()
        doc_emb = model.encode([text], convert_to_tensor=True)
    
    else:
        print("[extract_tags] Using pre-computed document embedding.")
        if not isinstance(doc_emb, torch.Tensor):
            doc_emb = torch.tensor(doc_emb, dtype=torch.float32)
        if doc_emb.dim() == 1:
            doc_emb = doc_emb.unsqueeze(0) 
    
    #
    # ✅ --- THESE LINES ARE NOW DELETED ---
    # model = get_embedding_model()
    # doc_emb = model.encode([text], convert_to_tensor=True)
    #
    
    # Convert stored embeddings to tensor
    cand_embs = torch.tensor(np.array(embeddings), dtype=torch.float32)
    
    # Compute cosine similarity
    # Now this line correctly uses the doc_emb from your logic block
    scores = util.cos_sim(doc_emb, cand_embs)[0]
    
    # ... (Rest of your function is correct) ...
    top_idx = torch.topk(scores, k=min(top_n, len(scores))).indices.tolist()
    
    top_tags_with_desc = [
        {"name": candidates[i], "description": descriptions[i], "score": scores[i].item()}
        for i in top_idx
    ]
    
    filtered_tags = []
    for tag_data in top_tags_with_desc:
        tag_name = tag_data['name']
        if not any((tag_name != other['name'] and tag_name in other['name']) for other in top_tags_with_desc):
            filtered_tags.append(tag_data)
    
    result = [
        tag for tag in filtered_tags
        if tag['score'] >= min_score
    ]
    
    print(f"[extract_tags] Extracted {len(result)} tags: {[t['name'] for t in result]}")
    return result