# utils/single_paper_rag.py (Enhanced RAG with context expansion)

from google import genai
import os
from dotenv import load_dotenv
from django.conf import settings
import numpy as np
from papers.models import PaperChunk
from pgvector.django import CosineDistance
from .semantic_search import get_model
from typing import List, Tuple

# --- Environment Setup ---
BASE_DIR = settings.BASE_DIR
load_dotenv(BASE_DIR / ".env")
api_key = os.getenv("GEMINI_API_KEY")

# ----------------------------
# Helper Functions
# ----------------------------

def get_surrounding_chunks(db_id: int, paper_id: int, window: int = 1) -> List[PaperChunk]:
    """
    Retrieve chunks before and after a given chunk to provide more context.
    Uses the chunk_id field from your model for ordering.
    """
    try:
        target_chunk = PaperChunk.objects.get(id=db_id)
        page_num = target_chunk.page
        target_chunk_id = target_chunk.chunk_id
        
        # Get chunks from nearby pages (window pages before and after)
        surrounding = PaperChunk.objects.filter(
            paper_id=paper_id,
            page__gte=max(1, page_num - window) if page_num else 1,
            page__lte=(page_num + window) if page_num else 999999,
        ).order_by('page', 'chunk_id')  # Order by page, then by chunk_id
        
        return list(surrounding)
    except Exception as e:
        print(f"Error getting surrounding chunks: {e}")
        return []


def deduplicate_chunks(chunks: List[PaperChunk]) -> List[PaperChunk]:
    """Remove duplicate chunks while preserving order."""
    seen = set()
    unique_chunks = []
    for chunk in chunks:
        if chunk.id not in seen:
            seen.add(chunk.id)
            unique_chunks.append(chunk)
    return unique_chunks


def rerank_chunks(query: str, chunks: List[Tuple[PaperChunk, float]]) -> List[Tuple[PaperChunk, float]]:
    """
    Simple reranking based on keyword overlap and distance.
    For production, consider using a cross-encoder model.
    """
    query_words = set(query.lower().split())
    
    reranked = []
    for chunk, distance in chunks:
        chunk_words = set(chunk.text.lower().split())
        overlap = len(query_words & chunk_words)
        # Combine distance with keyword overlap
        score = distance - (overlap * 0.01)  # Boost for keyword matches
        reranked.append((chunk, score))
    
    return sorted(reranked, key=lambda x: x[1])

# ----------------------------
# Enhanced RAG Query
# ----------------------------

def query_rag(
    paper_id: int, 
    user_query: str, 
    top_k: int = 5,  # Increased from 3
    use_context_expansion: bool = True,
    use_hybrid_mode: bool = True,  # Allow model to use external knowledge
    temperature: float = 0.3
):
    """
    Enhanced RAG pipeline with:
    - More chunks retrieved
    - Context expansion (surrounding chunks)
    - Optional hybrid mode (paper + model knowledge)
    - Better prompting
    """
    
    # 1. Embed query
    embed_model = get_model()
    if embed_model is None:
        return "Sorry, the embedding model is currently unavailable."
    
    query_emb = embed_model.encode([user_query], convert_to_numpy=True)[0]
    query_emb_list = query_emb.tolist()

    # 2. Retrieve initial chunks with scores
    try:
        retrieved = (
            PaperChunk.objects
            .filter(paper_id=paper_id)
            .annotate(distance=CosineDistance("embedding", query_emb_list))
            .order_by("distance")[:top_k]
        )
        
        chunks_with_scores = [(chunk, chunk.distance) for chunk in retrieved]
        
        # Optional: Rerank results
        chunks_with_scores = rerank_chunks(user_query, chunks_with_scores)
        
    except Exception as e:
        print(f"Error during retrieval: {e}")
        return "Sorry, I had trouble searching the paper's contents."

    if not chunks_with_scores:
        return "I couldn't find relevant information in this paper."

    # 3. Expand context with surrounding chunks
    all_chunks = []
    if use_context_expansion:
        for chunk, score in chunks_with_scores:
            surrounding = get_surrounding_chunks(chunk.id, paper_id, window=1)
            all_chunks.extend(surrounding)
    else:
        all_chunks = [chunk for chunk, _ in chunks_with_scores]
    
    # Deduplicate and sort by page/position
    all_chunks = deduplicate_chunks(all_chunks)
    all_chunks.sort(key=lambda x: (x.page if x.page else 0, x.chunk_id))

    # 4. Build enhanced context with better structure
    context_str = ""
    current_page = None
    
    for chunk in all_chunks:
        if chunk.page != current_page:
            context_str += f"\n{'='*60}\n📄 PAGE {chunk.page}\n{'='*60}\n\n"
            current_page = chunk.page
        context_str += f"{chunk.text}\n\n"

    # 5. Build improved prompt
    if use_hybrid_mode:
        prompt = f"""You are an expert research assistant analyzing a scientific paper.

**CONTEXT FROM THE PAPER:**
{context_str}

**USER QUESTION:** 
{user_query}

**INSTRUCTIONS:**
1. Primarily base your answer on the provided context from the paper
2. Always cite page numbers when referencing specific information (e.g., "On page 5, the authors discuss...")
3. If the paper doesn't fully address the question, you may supplement with general knowledge, but clearly distinguish between:
   - Information from the paper (cite pages)
   - General knowledge you're adding (state "Based on general knowledge...")
4. If the paper contradicts general knowledge, prioritize what the paper says
5. Be precise and academic in tone
6. If you're uncertain, say so

**ANSWER:**"""
    else:
        prompt = f"""You are an expert research assistant. Answer based ONLY on the following context from the paper.
Always reference page numbers when providing specific information.

**CONTEXT:**
{context_str}

**QUESTION:** {user_query}

**ANSWER:**"""

    # 6. Generate with Gemini
    if not api_key:
        return "Sorry, AI generation service not configured."

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",  # Using latest model
            contents=prompt,
            config={
                "temperature": temperature,
                "max_output_tokens": 2048,
            }
        )
        
        # Add metadata about retrieval
        answer = response.text
        metadata = f"\n\n---\n*Retrieved from {len(all_chunks)} chunks across {len(set(c.page for c in all_chunks))} pages*"
        
        return answer + metadata
        
    except Exception as e:
        print(f"Error during generation: {e}")
        return "Sorry, I encountered an error generating an answer."


# ----------------------------
# Optional: Multi-query RAG
# ----------------------------

def multi_query_rag(paper_id: int, user_query: str):
    """
    Generate multiple query variations to retrieve more diverse results.
    """
    if not api_key:
        return query_rag(paper_id, user_query)
    
    try:
        client = genai.Client(api_key=api_key)
        
        # Generate query variations
        variation_prompt = f"""Generate 3 different ways to rephrase this question to search a research paper:
"{user_query}"

Return only the 3 questions, numbered 1-3, nothing else."""
        
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=variation_prompt
        )
        
        queries = [user_query]  # Include original
        for line in response.text.split('\n'):
            if line.strip() and any(line.startswith(str(i)) for i in range(1, 4)):
                queries.append(line.split('.', 1)[1].strip())
        
        # Retrieve with all queries and combine results
        embed_model = get_model()
        all_chunks = set()
        
        for q in queries[:3]:  # Limit to avoid too many queries
            query_emb = embed_model.encode([q], convert_to_numpy=True)[0]
            chunks = (
                PaperChunk.objects
                .filter(paper_id=paper_id)
                .annotate(distance=CosineDistance("embedding", query_emb.tolist()))
                .order_by("distance")[:3]
            )
            all_chunks.update(chunks)
        
        # Now use combined chunks for generation
        # (Implement similar to query_rag with the combined chunk set)
        
    except Exception as e:
        print(f"Multi-query failed, falling back: {e}")
        return query_rag(paper_id, user_query)