"""
Paper Summarization Utility
Generates summaries from paper content using local Llama model (Gemma 3)
Updated to join ALL chunks and use full 32k context window
Now uses streaming chat completion format
"""

import os
from llama_cpp import Llama

_llm = None 
# ----------- Load model once globally -----------
def get_llm():
    """Load Llama model on first use, then cache it."""
    global _llm
    if _llm is None:
        print("🦙 Loading local Llama model (Gemma 3)... this may take a bit")
        try:
            _llm = Llama.from_pretrained(
                repo_id="unsloth/gemma-3-1b-it-GGUF",
                filename="gemma-3-1b-it-BF16.gguf",
                seed=4,
                n_ctx=32000,
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
	Generate a streamed summary for the paper using Gemma 3.
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
	
	# ---- Step 3: Summarize using chat interface ----
	output = llm.create_chat_completion(
		messages=[
			{
				"role": "system",
				"content": "You are an academic summarizer that writes clear and concise summaries."
			},
			{
				"role": "user",
				"content": f"Summarize this paper concisely and detailed:\n\n{all_text}"
			}
		],
		stream=True,
		seed=2,
	)

	# ---- Step 4: Stream output live ----
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
	"""
	llm = get_llm() 
	import fitz
	doc = fitz.open(pdf_path)
	all_text = " ".join(page.get_text() for page in doc)
	title = os.path.splitext(os.path.basename(pdf_path))[0]

	output = llm.create_chat_completion(
		messages=[
			{
				"role": "system",
				"content": "You are an academic summarizer that writes clear and concise summaries."
			},
			{
				"role": "user",
				"content": f"Summarize this paper concisely and detailed:\n\n{all_text}"
			}
		],
		stream=True,
		seed=2,
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
		"inference_mode": "local_llama_cpp_stream",
	}
