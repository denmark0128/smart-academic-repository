import re
import json
# ❌ REMOVE: from sentence_transformers import util
# ❌ REMOVE: import torch
from google import genai
from google.genai import types
from .semantic_search import get_model
from django.core.cache import cache
from papers.models import Tag
import numpy as np
from staff.utils import get_search_settings 

# --- GenAI Settings ---
GENAI_EMBEDDING_MODEL = 'gemini-embedding-001'
# --- End GenAI Settings ---

_client = None
_embedding_model_name = None

def get_embedding_model():
  """
  Get the configured GenAI client and model name.
  Caches the client locally.
  """
  global _client, _embedding_model_name
  if _client is None:
    _client = get_model()
    _embedding_model_name = GENAI_EMBEDDING_MODEL
  return _client, _embedding_model_name


def cosine_similarity(a, b):
  """
  Compute cosine similarity between two vectors or between a vector and a matrix.
  a: shape (n,) or (1, n)
  b: shape (m, n)
  returns: shape (m,) - similarity scores
  """
  a = np.array(a)
  b = np.array(b)
  
  # Ensure a is 1D
  if a.ndim == 2:
    a = a.flatten()
  
  # Compute dot product
  dot_product = np.dot(b, a)
  
  # Compute norms
  norm_a = np.linalg.norm(a)
  norm_b = np.linalg.norm(b, axis=1)
  
  # Avoid division by zero
  return dot_product / (norm_a * norm_b + 1e-8)


def extract_tags(text=None, doc_emb=None, top_n=None, min_score=None): 
  """
  Extract relevant tags from text OR a pre-computed embedding using GenAI.
  """
  # 1. Get Settings
  search_settings = get_search_settings()
  if top_n is None:
    top_n = search_settings.tag_extraction_top_n
  if min_score is None:
    min_score = search_settings.tag_extraction_min_score
  
  print(f"top n: {top_n}")
  print(f"min_score: {min_score}")
  
  # Cache loading
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
  
  # 2. Encode Text
  if doc_emb is None:
    if not text or not text.strip():
      print("[extract_tags] No text or embedding provided.")
      return []
    
    print("[extract_tags] Encoding provided text using GenAI...")
    client, model_name = get_embedding_model()

    if not client:
      print("❌ GenAI Client not available.")
      return []

    try:
      response = client.models.embed_content(
        model=model_name,
        contents=[text],
        config=types.EmbedContentConfig(task_type="CLASSIFICATION")
      )
      
      # ✅ Access the embedding correctly based on response structure
      if hasattr(response, 'embeddings'):
        doc_emb = np.array(response.embeddings[0].values, dtype=np.float32)
      elif hasattr(response, 'values'):
        doc_emb = np.array(response.values, dtype=np.float32)
      else:
        print(f"❌ Unexpected response structure: {dir(response)}")
        return []
        
    except Exception as e:
      print(f"❌ Failed to embed text with GenAI: {e}")
      import traceback
      traceback.print_exc()
      return []

  else:
    print("[extract_tags] Using pre-computed document embedding.")
    doc_emb = np.array(doc_emb, dtype=np.float32)
  
  # 3. Compute Similarity using NumPy
  cand_embs = np.array(embeddings, dtype=np.float32)
  
  # ✅ Use our custom cosine_similarity function instead of util.cos_sim
  scores = cosine_similarity(doc_emb, cand_embs)
  
  # 4. Get top N
  top_idx = np.argsort(scores)[::-1][:top_n]
  
  top_tags_with_desc = [
    {"name": candidates[i], "description": descriptions[i], "score": float(scores[i])}
    for i in top_idx
  ]
  
  # 5. Filter nested tags
  filtered_tags = []
  for tag_data in top_tags_with_desc:
    tag_name = tag_data['name']
    if not any((tag_name != other['name'] and tag_name in other['name']) for other in top_tags_with_desc):
      filtered_tags.append(tag_data)
  
  # 6. Filter by min_score
  result = [
    tag for tag in filtered_tags
    if tag['score'] >= min_score
  ]
  
  print(f"[extract_tags] Extracted {len(result)} tags: {[t['name'] for t in result]}")
  return result