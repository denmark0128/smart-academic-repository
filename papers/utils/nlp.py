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

# Add general topic tags
GENERAL_TOPICS = [
    "computer science", "psychology", "", "biology",
    "physics", "mathematics", "engineering", "chemistry", "social science", "economics",
    "education", "political science", "philosophy", "history", "art", "literature"
]

BANK_OF_WORDS = load_bank_of_words()

def extract_tags(text, top_n=5, min_score=0.5):
    # Use the bank of words as tag candidates
    candidates = list(BANK_OF_WORDS)
    if not candidates:
        return []
    # Embed document and candidates
    model = get_mpnet_model()
    doc_emb = model.encode([text], convert_to_tensor=True)
    cand_embs = model.encode(candidates, convert_to_tensor=True)
    # Compute cosine similarity
    scores = util.cos_sim(doc_emb, cand_embs)[0]
    top_idx = torch.topk(scores, k=min(top_n, len(scores))).indices.tolist()
    top_tags = [candidates[i] for i in top_idx]
    # Remove tags that are substrings of longer tags
    top_tags = [t for t in top_tags if not any((t != o and t in o) for o in top_tags)]
    return [t for t in top_tags if scores[top_idx[top_tags.index(t)]] >= min_score]
