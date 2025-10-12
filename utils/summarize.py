import os
import re
import fitz  # PyMuPDF
from llama_cpp import Llama
import textwrap

# ----------- Load model once globally -----------
print("🦙 Loading local Llama model (Gemma 3)... this may take a bit")
llm = Llama.from_pretrained(
    repo_id="unsloth/gemma-3-1b-it-GGUF",
    filename="gemma-3-1b-it-BF16.gguf",
    n_ctx=32000,
    n_threads=8,
)
print("✅ Model loaded and ready.")


# ----------- PDF Text Extraction -----------
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return " ".join(text.split())


# ----------- Summarize Full Paper -----------
def summarize_full_text(text, title=None):
    title_str = f" titled '{title}'" if title else ""
    prompt = textwrap.dedent(f"""
    You are an expert academic summarizer.
    Summarize the following research paper{title_str}.
    
    Rules:
    - Write only the summary text, nothing else.
    - Do NOT include any introductions like “Okay, here’s a summary...”.
    - Do NOT include labels such as “Summary:” or “Keywords:”.
    - Do NOT use Markdown formatting like **bold** or *italics*.
    - Preserve paragraph breaks for readability.

    --- Paper Text ---
    {text}
    """)

    print("💻 Generating full-text summary...")
    out = llm.create_completion(prompt=prompt)
    content = out["choices"][0]["text"].strip()

    # Clean out any hidden thinking tags or markdown stars
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    summary = content.replace("**", "").replace("*", "").strip()

    return summary



# ----------- Main pipeline (returns dict) -----------
def summarize_pdf_to_json(pdf_path):
    text = extract_text_from_pdf(pdf_path)
    summary = summarize_full_text(text, os.path.basename(pdf_path))

    result = {
        "file": os.path.basename(pdf_path),
        "title": os.path.splitext(os.path.basename(pdf_path))[0],
        "summary": summary,
        "inference_mode": "local_llama_cpp_fulltext",
    }

    print(f"✅ Summary generated for: {os.path.basename(pdf_path)}")
    return result
