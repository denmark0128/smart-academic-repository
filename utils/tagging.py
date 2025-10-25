import spacy
import re
from spacy.lang.en.stop_words import STOP_WORDS
from sentence_transformers import SentenceTransformer, util
import torch
from utils.semantic_search import get_model

nlp = spacy.load("en_core_web_sm")
_mpnet_model = None

def get_mpnet_model():
    global _mpnet_model
    if _mpnet_model is None:
        _mpnet_model = get_model()
    return _mpnet_model

EXTRA_STOPWORDS = {
    "this paper", "our approach", "application", "approach", "paper", "study", "result", "method", "methods", "conclusion", "introduction", "discussion", "analysis", "effect", "effects", "data", "research", "author", "authors", "review", "evidence", "findings", "outcome", "outcomes", "association", "associations", "risk", "risks", "group", "groups", "disease", "diseases", "patients", "participant", "participants", "use", "impact", "impacts", "role", "case", "cases", "model", "models", "process", "processes", "result", "results", "study", "studies", "conclusion", "conclusions", "objective", "objectives", "aim", "aims", "background", "purpose", "summary", "evidence", "review", "meta-analysis", "systematic review", "this set", "this work", "their correspondence", "english-speaking audiences", "large-language model", "new russian", "other russian sites", "other russian", "other outcomes", "any health outcome", "any health outcomes", "any adult population", "all settings", "all countries", "all cause mortality", "all available studies", "reference lists", "potential biases", "existing evidence", "observed associations", "observational research", "observational studies", "interventional research", "interventional studies", "systematic reviews", "summary estimates", "umbrella review", "umbrella reviews", "meta-analyses", "meta analyses", "systematic review registration",
    # Academic meta-language
    "paper", "article", "publication", "manuscript", "document", 
    "section", "chapter", "figure", "table", "appendix",
    "reference", "references", "citation", "citations",
    "abstract", "keyword", "keywords", "title",
    "significant", "significantly", "significance", "important", "importantly",
    "current", "previous", "present", "future", "recent", "recently",
    "research", "investigation", "examination", "exploration",
    "framework", "theory", "theories", "concept", "concepts",
    "literature", "dataset", "sample", "samples",
    "significant difference", "statistical significance", "sample size",
    "research question", "research questions", "hypothesis", "hypotheses",
    "contribution", "contributions", "novelty", "innovation",
    "performance", "evaluation", "experiment", "experiments",
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

def load_bank_of_words(path='bank_of_words.txt'):
    bank = set()
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                word = line.strip().lower()
                if word and not word.startswith('#'):
                    bank.add(word)
    except Exception:
        pass
    return bank

GENERAL_TOPICS = [
    "computer science", "psychology", "medicine", "biology",
    "physics", "mathematics", "engineering", "chemistry", "social science", "economics",
    "education", "political science", "philosophy", "history", "art", "literature"
]

BANK_OF_WORDS = load_bank_of_words().union(set(GENERAL_TOPICS))

def calculate_keyword_presence(text, candidates):
    """
    Calculate how strongly each candidate appears in the text.
    Returns dict of candidate -> presence_score (0-1+)
    """
    if not text:
        return {c: 0.0 for c in candidates}
    
    text_lower = text.lower()
    # Extract words, preserving multi-word terms
    text_words = set(re.findall(r'\b\w+\b', text_lower))
    
    presence_scores = {}
    for candidate in candidates:
        candidate_lower = candidate.lower()
        candidate_words = candidate_lower.split()
        
        # Exact phrase match (highest score)
        exact_count = text_lower.count(candidate_lower)
        
        # Word-level overlap
        word_matches = sum(1 for word in candidate_words if word in text_words)
        word_ratio = word_matches / len(candidate_words) if candidate_words else 0
        
        # Combined score: exact matches heavily weighted
        presence_scores[candidate] = min(exact_count * 3.0 + word_ratio, 5.0)
    
    return presence_scores

def extract_tags_from_paper(title, abstract, top_n=5, min_semantic_score=0.50, require_keyword_presence=True):
    """
    Extract tags from a paper's title and abstract.
    Optimized for short academic text (title + abstract typically < 500 words).
    
    Args:
        title: Paper title (string)
        abstract: Paper abstract (string)
        top_n: Number of tags to return
        min_semantic_score: Minimum semantic similarity (0-1)
        require_keyword_presence: If True, tags must appear in title/abstract
    
    Returns:
        List of tag strings
    """
    candidates = list(BANK_OF_WORDS)
    if not candidates:
        return []
    
    # Combine title and abstract, weight title more heavily
    title = title or ""
    abstract = abstract or ""
    
    # Title appears 3x for emphasis (title is most informative)
    combined_text = f"{title} {title} {title} {abstract}"
    
    if not combined_text.strip():
        return []
    
    # Get semantic similarity scores
    model = get_mpnet_model()
    doc_emb = model.encode([combined_text], convert_to_tensor=True)
    cand_embs = model.encode(candidates, convert_to_tensor=True)
    semantic_scores = util.cos_sim(doc_emb, cand_embs)[0]
    
    # Calculate keyword presence (from original text, not weighted)
    original_text = f"{title} {abstract}"
    presence_scores = calculate_keyword_presence(original_text, candidates)
    
    # Combine scores
    scored_tags = []
    for i, candidate in enumerate(candidates):
        semantic_score = float(semantic_scores[i])
        presence_score = presence_scores[candidate]
        
        # Skip if semantic score too low
        if semantic_score < min_semantic_score:
            continue
        
        # If requiring keyword presence, skip tags not in text
        if require_keyword_presence and presence_score < 0.3:
            continue
        
        # Combined score: semantic is primary, presence gives boost
        combined_score = semantic_score + (presence_score * 0.1)
        scored_tags.append((candidate, combined_score, semantic_score, presence_score))
    
    if not scored_tags:
        return []
    
    # Sort by combined score
    scored_tags.sort(key=lambda x: x[1], reverse=True)
    
    # Remove substring duplicates
    final_tags = []
    for tag, combined, semantic, presence in scored_tags:
        # Skip if this is a substring of an already selected tag
        is_substring = any(tag != existing and tag in existing for existing in final_tags)
        
        # Skip if a better-scored substring already exists
        has_better_substring = any(
            existing != tag and existing in tag and 
            any(t[0] == existing and t[1] > combined for t in scored_tags)
            for existing in final_tags
        )
        
        if not is_substring and not has_better_substring:
            final_tags.append(tag)
        
        if len(final_tags) >= top_n:
            break
    
    return final_tags


def extract_tags_with_chunks(paper_model, chunk_limit=10, top_n=5, min_semantic_score=0.50):
    """
    Extract tags using title, abstract, AND selected paper chunks for extra context.
    Use this for better accuracy when chunks are available.
    
    Args:
        paper_model: Django Paper model instance
        chunk_limit: How many chunks to sample for context (default: 10)
        top_n: Number of tags to return
        min_semantic_score: Minimum semantic similarity threshold
    
    Returns:
        List of tag strings
    """
    candidates = list(BANK_OF_WORDS)
    if not candidates:
        return []
    
    title = paper_model.title or ""
    abstract = paper_model.abstract or ""
    
    # Get some chunks for additional context (sample from different parts)
    chunks = paper_model.chunks.all()[:chunk_limit]
    chunk_text = " ".join(chunk.text for chunk in chunks)[:2000]  # Limit chunk text
    
    # Weight: Title (3x) + Abstract (2x) + Chunks (1x)
    combined_text = f"{title} {title} {title} {abstract} {abstract} {chunk_text}"
    
    if not combined_text.strip():
        return []
    
    # Semantic similarity
    model = get_mpnet_model()
    doc_emb = model.encode([combined_text], convert_to_tensor=True)
    cand_embs = model.encode(candidates, convert_to_tensor=True)
    semantic_scores = util.cos_sim(doc_emb, cand_embs)[0]
    
    # Keyword presence (check in title, abstract, and chunks)
    full_text = f"{title} {abstract} {chunk_text}"
    presence_scores = calculate_keyword_presence(full_text, candidates)
    
    # Combine scores
    scored_tags = []
    for i, candidate in enumerate(candidates):
        semantic_score = float(semantic_scores[i])
        presence_score = presence_scores[candidate]
        
        # More lenient with chunks - semantic similarity is more reliable
        if semantic_score < min_semantic_score:
            continue
        
        combined_score = semantic_score + (presence_score * 0.1)
        scored_tags.append((candidate, combined_score, semantic_score, presence_score))
    
    if not scored_tags:
        return []
    
    scored_tags.sort(key=lambda x: x[1], reverse=True)
    
    # Remove duplicates
    final_tags = []
    for tag, combined, semantic, presence in scored_tags:
        is_substring = any(tag != existing and tag in existing for existing in final_tags)
        has_better_substring = any(
            existing != tag and existing in tag and 
            any(t[0] == existing and t[1] > combined for t in scored_tags)
            for existing in final_tags
        )
        
        if not is_substring and not has_better_substring:
            final_tags.append(tag)
        
        if len(final_tags) >= top_n:
            break
    
    return final_tags


def extract_tags(text, top_n=5, min_score=0.50):
    """
    Legacy function - extracts from any text.
    For Paper models, use extract_tags_from_paper() or extract_tags_with_chunks() instead.
    """
    candidates = list(BANK_OF_WORDS)
    if not candidates:
        return []
    
    if not text or not text.strip():
        return []
    
    # Limit text length
    text = text[:2000] if len(text) > 2000 else text
    
    model = get_mpnet_model()
    doc_emb = model.encode([text], convert_to_tensor=True)
    cand_embs = model.encode(candidates, convert_to_tensor=True)
    scores = util.cos_sim(doc_emb, cand_embs)[0]
    
    # Filter by minimum score
    valid_indices = [i for i, score in enumerate(scores) if score >= min_score]
    
    if not valid_indices:
        return []
    
    # Sort and take top N
    valid_indices.sort(key=lambda i: scores[i], reverse=True)
    top_indices = valid_indices[:top_n * 2]
    
    tag_score_pairs = [(candidates[i], float(scores[i])) for i in top_indices]
    
    # Remove duplicates
    filtered_tags = []
    for tag, score in tag_score_pairs:
        if not any(tag != existing and tag in existing for existing, _ in filtered_tags):
            if not any(existing != tag and existing in tag and existing_score > score 
                      for existing, existing_score in filtered_tags):
                filtered_tags.append((tag, score))
        
        if len(filtered_tags) >= top_n:
            break
    
    return [tag for tag, score in filtered_tags]