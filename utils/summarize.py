import os
from llama_cpp import Llama
import fitz
from staff.utils import get_llama_settings  # <-- Following your pattern

_llm = None 
# ----------- Load model once globally -----------
def get_llm():
    """Load Llama model on first use, then cache it."""
    global _llm
    if _llm is None:
        # ✅ Get settings dynamically
        settings = get_llama_settings()
        
        print(f"🦙 Loading local Llama model ({settings.repo_id})... this may take a bit")
        try:
            _llm = Llama.from_pretrained(
                repo_id=settings.repo_id,               # <-- Changed
                filename=settings.model_filename,       # <-- Changed
                seed=settings.model_seed,               # <-- Changed
                n_ctx=settings.n_ctx,                   # <-- Changed
            )
            print("✅ Model loaded and ready.")
        except Exception as e:
            print(f"❌ Failed to load model: {e}")
            _llm = None
    return _llm


def get_paper_text(paper):
    """
    Extract and join ONLY chunk text (ignore title and abstract).
    """
    chunks = paper.chunks.all().order_by("chunk_id")

    if chunks.exists():
        all_text = " ".join(chunk.text for chunk in chunks if chunk.text)
        print(f"[Summarizer] Joined {len(chunks)} chunks")
    else:
        all_text = ""
        print("[Summarizer] No chunks found")

    print(f"[Summarizer] Total text length: {len(all_text):,} chars")
    return all_text


def generate_summary(paper):
    """
    Generate a streamed summary for the paper using settings from the database.
    """
    llm = get_llm() 
    if not llm:
        print("[Summarizer] ERROR: Model not loaded")
        return None

    all_text = get_paper_text(paper)
    if not all_text.strip():
        print("[Summarizer] No text found to summarize.")
        return None

    print(f"[Summarizer] Generating summary for: {paper.title}")
    
    # ✅ Get settings dynamically
    settings = get_llama_settings()

    # --- Build generation arguments from settings ---
    generation_args = {
        "stream": True,
        "seed": settings.generation_seed,  # <-- Changed
    }
    
    # Add optional params from settings ONLY if they are set (not None)
    if settings.temperature is not None:
        generation_args["temperature"] = settings.temperature
    if settings.max_tokens is not None:
        generation_args["max_tokens"] = settings.max_tokens
    if settings.top_p is not None:
        generation_args["top_p"] = settings.top_p

    # ---- Summarize using chat interface ----
    output = llm.create_chat_completion(
        messages=[
            {
                "role": "system",
                "content": settings.system_prompt  # <-- Changed
            },
            {
                "role": "user",
                "content": settings.user_prompt_template.format(text=all_text) # <-- Changed
            }
        ],
        **generation_args
    )

    # ---- Stream output live ----
    result = ""
    for chunk in output:
        delta = chunk["choices"][0]["delta"]
        if "content" in delta:
            print(delta["content"], end="", flush=True)
            result += delta["content"]

    print("\n\n=== Final Output ===")
    print(result)

    return result


def summarize_pdf_to_json(pdf_path):
    """
    Legacy function for direct PDF summarization.
    Now uses settings from the database.
    """
    llm = get_llm() 
    doc = fitz.open(pdf_path)
    all_text = " ".join(page.get_text() for page in doc)
    title = os.path.splitext(os.path.basename(pdf_path))[0]

    # ✅ Get settings dynamically
    settings = get_llama_settings()

    # --- Build generation arguments from settings ---
    generation_args = {
        "stream": True,
        "seed": settings.generation_seed, # <-- Changed
    }
    
    if settings.temperature is not None:
        generation_args["temperature"] = settings.temperature
    if settings.max_tokens is not None:
        generation_args["max_tokens"] = settings.max_tokens
    if settings.top_p is not None:
        generation_args["top_p"] = settings.top_p

    output = llm.create_chat_completion(
        messages=[
            {
                "role": "system",
                "content": settings.system_prompt  # <-- Changed
            },
            {
                "role": "user",
                "content": settings.user_prompt_template.format(text=all_text) # <-- Changed
            }
        ],
        **generation_args
    )

    result = ""
    for chunk in output:
        delta = chunk["choices"][0]["delta"]
        if "content" in delta:
            print(delta["content"], end="", flush=True)
            result += delta["content"]

    print("\n\n=== Final Output ===")
    print(result)

    return {
        "file": os.path.basename(pdf_path),
        "title": title,
        "summary": result,
        "inference_mode": "local_llama_cpp_stream_db_settings", # <-- Updated
    }