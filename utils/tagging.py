import re
from sentence_transformers import util
import torch
import json
# ✅ IMPORT GenAI
from google import genai
from google.genai import types
from .semantic_search import get_model # get_model now returns genai.Client
from django.core.cache import cache
from papers.models import Tag
import numpy as np
from staff.utils import get_search_settings 

# --- GenAI Settings ---
GENAI_EMBEDDING_MODEL = 'gemini-embedding-001' # Using the 768-dim model
# --- End GenAI Settings ---

_client = None # <-- Renamed to client
_embedding_model_name = None # To hold the model name for the embedding call

def get_embedding_model():  # <-- Modified
  """
  Get the configured GenAI client and model name.
  Caches the client locally.
  """
  global _client, _embedding_model_name
  if _client is None:
    _client = get_model() # returns the genai.Client instance from semantic_search.py
    _embedding_model_name = GENAI_EMBEDDING_MODEL
  return _client, _embedding_model_name

# ... keep all your existing constants and functions ...

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
  
  # ... (Your cache loading code remains the same) ...
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
  
  # 2. Encode Text (MODIFIED)
  if doc_emb is None:
    if not text or not text.strip():
      print("[extract_tags] No text or embedding provided.")
      return []
    
    print("[extract_tags] Encoding provided text using GenAI...")
    # ✅ Get GenAI Client and model name
    client, model_name = get_embedding_model()

    if not client:
      print("❌ GenAI Client not available.")
      return []

    try:
      # Use RETRIEVAL_QUERY task type for the document/query being tagged
      response = client.models.embed_content(
        model=model_name,
        contents=[text],
        task_type="CLASSIFICATION"
      )
      # Convert list output to PyTorch Tensor for compatibility with util.cos_sim
      doc_emb = torch.tensor(response['embedding'], dtype=torch.float32)
    except Exception as e:
      print(f"❌ Failed to embed text with GenAI: {e}")
      return []

  else:
    print("[extract_tags] Using pre-computed document embedding.")
    if not isinstance(doc_emb, torch.Tensor):
      doc_emb = torch.tensor(doc_emb, dtype=torch.float32)
    if doc_emb.dim() == 1:
      doc_emb = doc_emb.unsqueeze(0) 
  
  # 3. Compute Similarity (Rest of the logic remains the same)
  # Convert stored embeddings (which are RETRIEVAL_DOCUMENT type) to tensor
  cand_embs = torch.tensor(np.array(embeddings), dtype=torch.float32)
  
  # Compute cosine similarity
  scores = util.cos_sim(doc_emb, cand_embs)[0]
  
  # ... (Rest of your function is correct, calculating top_idx, filtering, etc.) ...
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