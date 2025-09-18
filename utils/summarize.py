import os
import re
import fitz  # PyMuPDF
import json
from dotenv import load_dotenv
from transformers import AutoTokenizer
from huggingface_hub import InferenceClient

# Setup tokenizer and HF client

load_dotenv()

#tokenizer = AutoTokenizer.from_pretrained("HuggingFaceTB/SmolLM3-3B")
client = InferenceClient(
    provider="hf-inference",
    api_key = os.environ.get("HF_TOKEN")
)

# ----------- Extract PDF text -----------
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return " ".join(text.split())

# ----------- Count tokens -----------
def count_tokens(text):
    return len(tokenizer.encode(text))

# ----------- Summarize text -----------
def summarize_text(text):
    full_prompt = f"Summarize the following academic paper in a structured and concise format. Focus on the research objective, methodology, key findings, and conclusions. Avoid commentary or irrelevant details.:\n{text}"
    completion = client.chat.completions.create(
        model="HuggingFaceTB/SmolLM3-3B",
        messages=[{"role": "user", "content": full_prompt}],
    )
    raw_output = completion.choices[0].message.content
    return re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()

# ----------- Save JSON -----------
def save_summary_json(output_path, metadata):
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"✅ Summary saved to: {output_path}")

# ----------- Full pipeline -----------
def summarize_pdf_to_json(pdf_path, max_tokens=64000):
    text = extract_text_from_pdf(pdf_path)
    token_count = count_tokens(text)
    print(f"🔢 Token count: {token_count}")

    if token_count > max_tokens:
        print(f"⚠️ Truncating to {max_tokens} tokens...")
        tokens = tokenizer.encode(text)[:max_tokens]
        text = tokenizer.decode(tokens)

    summary = summarize_text(text)

    metadata = {
        "file": os.path.basename(pdf_path),
        "title": os.path.splitext(os.path.basename(pdf_path))[0],
        "token_count": token_count,
        "truncated": token_count > max_tokens,
        "summary": summary,
    }

    output_file = os.path.splitext(pdf_path)[0] + "_summary.json"
    save_summary_json(output_file, metadata)

