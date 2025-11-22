# utils/single_paper_rag.py (Enhanced RAG with Gemini embeddings)

from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
from django.conf import settings
import numpy as np
from papers.models import PaperChunk
from pgvector.django import CosineDistance
from typing import List, Tuple

# --- Environment Setup ---
BASE_DIR = settings.BASE_DIR
load_dotenv(BASE_DIR / ".env")
api_key = os.getenv("GEMINI_API_KEY")
GENAI_EMBEDDING_MODEL = 'gemini-embedding-001'  # Match your working module

# ----------------------------
# GenAI Client
# ----------------------------

def get_genai_client():
    """
    Returns the GenAI Client instance.
    """
    try:
        # The client will automatically pick up the API key from environment variables
        client = genai.Client()
        print("✅ GenAI Client loaded.")
        return client
    except Exception as e:
        print(f"❌ Failed to initialize GenAI Client: {e}")
        return None


# ----------------------------
# Embedding Functions
# ----------------------------

def get_gemini_embedding(text: str, task_type: str = "RETRIEVAL_QUERY") -> np.ndarray:
    """
    Get embedding from Gemini API for a single text.
    
    Args:
        text: Text to embed
        task_type: One of "RETRIEVAL_DOCUMENT" or "RETRIEVAL_QUERY"
    """
    client = get_genai_client()
    if not client:
        raise ValueError("Gemini API client not initialized. Check GEMINI_API_KEY.")
    
    try:
        response = client.models.embed_content(
            model=GENAI_EMBEDDING_MODEL,
            contents=[text],
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=768
            )
        )
        
        # Handle response structure (same as your working module)
        if hasattr(response, 'embeddings'):
            query_emb = np.array(response.embeddings[0].values)
        elif hasattr(response, 'values'):
            query_emb = np.array(response.values)
        else:
            print(f"❌ Unexpected response structure: {dir(response)}")
            raise ValueError("Unexpected embedding response structure")
        
        return query_emb
    except Exception as e:
        print(f"❌ Error getting Gemini embedding: {e}")
        import traceback
        traceback.print_exc()
        raise


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
    top_k: int = 5,
    use_context_expansion: bool = True,
    use_hybrid_mode: bool = True,
    temperature: float = 0.3
):
    """
    Enhanced RAG pipeline with Gemini embeddings:
    - Gemini gemini-embedding-001 for query encoding
    - More chunks retrieved
    - Context expansion (surrounding chunks)
    - Optional hybrid mode (paper + model knowledge)
    - Better prompting
    """
    
    # 1. Embed query using Gemini (matching your working module's approach)
    try:
        query_emb = get_gemini_embedding(user_query, task_type="RETRIEVAL_QUERY")
        query_emb_list = query_emb.tolist()
    except Exception as e:
        print(f"❌ Error embedding query: {e}")
        return "Sorry, I had trouble processing your question."

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
        print(f"❌ Error during retrieval: {e}")
        import traceback
        traceback.print_exc()
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
    client = get_genai_client()
    if not client:
        return "Sorry, AI generation service not configured."

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
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
        print(f"❌ Error during generation: {e}")
        import traceback
        traceback.print_exc()
        return "Sorry, I encountered an error generating an answer."


# ----------------------------
# Optional: Multi-query RAG
# ----------------------------

def multi_query_rag(paper_id: int, user_query: str):
    """
    Generate multiple query variations to retrieve more diverse results.
    Uses Gemini embeddings for all queries.
    """
    client = get_genai_client()
    if not client:
        return query_rag(paper_id, user_query)
    
    try:
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
        all_chunks = set()
        
        for q in queries[:3]:  # Limit to avoid too many queries
            try:
                query_emb = get_gemini_embedding(q, task_type="RETRIEVAL_QUERY")
                query_emb_list = query_emb.tolist()
                chunks = (
                    PaperChunk.objects
                    .filter(paper_id=paper_id)
                    .annotate(distance=CosineDistance("embedding", query_emb_list))
                    .order_by("distance")[:3]
                )
                all_chunks.update(chunks)
            except Exception as e:
                print(f"❌ Error with query '{q}': {e}")
                continue
        
        if not all_chunks:
            return query_rag(paper_id, user_query)
        
        # Sort chunks by page/position
        sorted_chunks = sorted(all_chunks, key=lambda x: (x.page if x.page else 0, x.chunk_id))
        
        # Build context
        context_str = ""
        current_page = None
        for chunk in sorted_chunks:
            if chunk.page != current_page:
                context_str += f"\n{'='*60}\n📄 PAGE {chunk.page}\n{'='*60}\n\n"
                current_page = chunk.page
            context_str += f"{chunk.text}\n\n"
        
        # Generate answer
        prompt = f"""You are an expert research assistant analyzing a scientific paper.

**CONTEXT FROM THE PAPER:**
{context_str}

**USER QUESTION:** 
{user_query}

**INSTRUCTIONS:**
1. Base your answer on the provided context
2. Always cite page numbers
3. Be precise and academic

**ANSWER:**"""
        
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt,
            config={"temperature": 0.3, "max_output_tokens": 2048}
        )
        
        return response.text + f"\n\n---\n*Multi-query retrieval: {len(all_chunks)} unique chunks*"
        
    except Exception as e:
        print(f"❌ Multi-query failed, falling back: {e}")
        import traceback
        traceback.print_exc()
        return query_rag(paper_id, user_query)