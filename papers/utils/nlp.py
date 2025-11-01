# utils/nlp.py
import spacy
import re
from spacy.lang.en.stop_words import STOP_WORDS
from sentence_transformers import util
import torch
import json
from utils.semantic_search import get_model
from django.core.cache import cache
from papers.models import Tag
import numpy as np

nlp = spacy.load("en_core_web_sm")
_mpnet_model = None

def get_mpnet_model():
    global _mpnet_model
    if _mpnet_model is None:
        _mpnet_model = get_model()  # returns the SentenceTransformer instance
    return _mpnet_model



EXTRA_STOPWORDS = {
    "this paper", "our approach", "application", "approach", "paper", "study", "result", "method", "methods", "conclusion", "introduction", "discussion", "analysis", "effect", "effects", "data", "research", "author", "authors", "review", "evidence", "findings", "outcome", "outcomes", "association", "associations", "risk", "risks", "group", "groups", "disease", "diseases", "patients", "participant", "participants", "use", "impact", "impacts", "role", "case", "cases", "model", "models", "process", "processes", "result", "results", "study", "studies", "conclusion", "conclusions", "objective", "objectives", "aim", "aims", "background", "purpose", "summary", "evidence", "review", "meta-analysis", "systematic review", "this set", "this work", "their correspondence", "english-speaking audiences", "large-language model", "new russian", "other russian sites", "other russian", "other outcomes", "any health outcome", "any health outcomes", "any adult population", "all settings", "all countries", "all cause mortality", "all available studies", "reference lists", "potential biases", "existing evidence", "observed associations", "observational research", "observational studies", "interventional research", "interventional studies", "systematic reviews", "summary estimates", "umbrella review", "umbrella reviews", "meta-analyses", "meta analyses", "systematic review registration"
}

COMMON_ENGLISH = set([
    'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she', 'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their', 'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go', 'me', 'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know', 'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could', 'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come', 'its', 'over', 'think', 'also', 'back', 'after', 'use', 'two', 'how', 'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want', 'because', 'any', 'these', 'give', 'day', 'most', 'us', 'is', 'are', 'was', 'were', 'has', 'had', 'did', 'does', 'having', 'being', 'been', 'may', 'might', 'must', 'shall', 'should', 'would', 'can', 'could', 'will', 'shall', 'do', 'did', 'does', 'done', 'doing', 'have', 'has', 'had', 'having', 'am', 'is', 'are', 'was', 'were', 'be', 'being', 'been', 'the', 'a', 'an', 'and', 'but', 'or', 'as', 'if', 'because', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now'
])

def clean_tag(tag):
    tag = tag.strip().replace("\n", " ")
    tag = re.sub(r'\s+', ' ', tag)
    tag = tag.lower()
    tag = re.sub(r'^(the|a|an)\s+', '', tag)
    if len(tag) <= 2:
        return None
    if tag in EXTRA_STOPWORDS or tag in STOP_WORDS or tag in COMMON_ENGLISH:
        return None
    words = tag.split()
    if not (1 <= len(words) <= 4):
        return None
    if re.fullmatch(r'\d{1,4}', tag):
        return None
    if re.fullmatch(r'\d{1,4}%?', tag):
        return None
    if re.fullmatch(r'\d{4}s', tag):
        return None
    if any(char.isdigit() for char in tag):
        return None
    doc = nlp(tag)
    if not all(token.pos_ in {"NOUN", "PROPN"} for token in doc):
        return None
    return tag

def load_bank_of_words(path='bank_of_words.json'):
    """
    Load tags from JSON file with 'name' and optional 'description'.
    Returns a set of cleaned tag names and a dict of {name: description}.
    """
    bank = set()
    descriptions = {}
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
            for item in data:
                name = item.get('name', '').strip()
                desc = item.get('description', '').strip()
                clean_name = clean_tag(name)
                if clean_name:
                    bank.add(clean_name)
                    descriptions[clean_name] = desc
    except Exception as e:
        print(f"[load_bank_of_words] Error loading JSON: {e}")
    return bank, descriptions


# Add general topic tags
GENERAL_TOPICS = [
    "computer science", "psychology", "biology",
    "physics", "mathematics", "engineering", "chemistry", "social science", "economics",
    "education", "political science", "philosophy", "history", "art", "literature"
]

BANK_OF_WORDS = load_bank_of_words()

def extract_tags(text, top_n=5, min_score=0.5):
    """
    Extract relevant tags from text using semantic similarity with pre-computed tag embeddings.
    Uses the tag descriptions (if available) for embedding similarity.
    """
    # Try to get cached tags with embeddings
    cache_key = 'active_tags_with_embeddings'
    cached_data = cache.get(cache_key)
    
    if cached_data is None:
        print("[extract_tags] Cache miss - loading tags from database")
        # Get active tags with embeddings from database
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
        # Cache for 1 hour
        cache.set(cache_key, cached_data, 3600)
        print(f"[extract_tags] Cached {len(candidates)} tags with embeddings")
    else:
        print(f"[extract_tags] Cache hit - using {len(cached_data['candidates'])} cached tags")
    
    candidates = cached_data['candidates']
    descriptions = cached_data['descriptions']
    embeddings = cached_data['embeddings']
    
    if not candidates:
        return []
    
    # Embed document only (not candidates - they're already embedded!)
    model = get_mpnet_model()
    doc_emb = model.encode([text], convert_to_tensor=True)
    
    # Convert stored embeddings to tensor
    cand_embs = torch.tensor(np.array(embeddings), dtype=torch.float32)
    
    # Compute cosine similarity
    scores = util.cos_sim(doc_emb, cand_embs)[0]
    
    # Get top K indices
    top_idx = torch.topk(scores, k=min(top_n, len(scores))).indices.tolist()
    
    # Use both candidate name and description for reference
    top_tags_with_desc = [
        {"name": candidates[i], "description": descriptions[i], "score": scores[i].item()}
        for i in top_idx
    ]
    
    # Remove tags that are substrings of longer tags
    filtered_tags = []
    for tag_data in top_tags_with_desc:
        tag_name = tag_data['name']
        if not any((tag_name != other['name'] and tag_name in other['name']) for other in top_tags_with_desc):
            filtered_tags.append(tag_data)
    
    # Filter by minimum score and sort by score (highest first)
    result = [
        tag for tag in filtered_tags
        if tag['score'] >= min_score
    ]
    
    print(f"[extract_tags] Extracted {len(result)} tags: {[t['name'] for t in result]}")
    return result
