#html_chunker.py
import os
import json
from bs4 import BeautifulSoup
import re

# --- CONFIG ---
MERGED_HTML = r"chm_e326c8ff/merged.html"
OUTPUT_JSON = "merged_chunks2.json"

# --- STEP 1: Extract sections from merged.html ---
def extract_sections_from_merged_html(merged_path):
    with open(merged_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "html.parser")

    content_div = soup.find("div", id="content")
    if not content_div:
        raise ValueError("No <div id='content'> found in merged.html")

    sections = []
    current_title = None
    current_text = []

    # Iterate through direct children of <div id="content">
    for elem in content_div.children:
        if elem.name == "h2":
            # Save previous section if valid
            if current_title and current_text and is_valid_section(current_title):
                section_type = classify_section(current_title)
                sections.append({
                    "title": current_title.strip(),
                    "text": " ".join(current_text).strip(),
                    "section_type": section_type
                })
            # Start new section
            current_title = elem.get_text(strip=True)
            current_text = []
        elif elem.name:
            current_text.append(elem.get_text(separator=" ", strip=True))

    # Add last section
    if current_title and current_text and is_valid_section(current_title):
        section_type = classify_section(current_title)
        sections.append({
            "title": current_title.strip(),
            "text": " ".join(current_text).strip(),
            "section_type": section_type
        })

    print(f"[+] Extracted {len(sections)} sections")
    return sections


# --- STEP 2: Section filter ---
def is_valid_section(title):
    t = title.lower()
    keep = (
        "abstract" in t
        or t.startswith("chapter i")
        or t.startswith("chapter ii")
        or t.startswith("chapter iii")
        or t.startswith("chapter iv")
        or t.startswith("chapter v")
    )
    skip = any(x in t for x in ["figure", "table", "appendix", "bibliography", "references"])
    return keep and not skip


# --- STEP 3: Section classifier ---
def classify_section(title):
    t = title.lower().strip()

    if "abstract" in t:
        return "abstract"
    elif re.match(r"chapter\s*i\b", t):
        return "introduction"
    elif re.match(r"chapter\s*ii\b", t) or "review of related" in t or "related studies" in t:
        return "rrl"
    elif re.match(r"chapter\s*iii\b", t):
        return "methodology"
    elif re.match(r"chapter\s*iv\b", t):
        return "results"
    elif re.match(r"chapter\s*v\b", t):
        return "conclusion"
    else:
        return "other"


# --- STEP 4: Chunk text ---
def chunk_text(text, max_chars=1000):
    sentences = text.split(". ")
    chunks, current = [], ""

    for s in sentences:
        if len(current) + len(s) < max_chars:
            current += s + ". "
        else:
            chunks.append(current.strip())
            current = s + ". "
    if current:
        chunks.append(current.strip())

    return chunks


# --- STEP 5: Process and save ---
def process_html_to_chunks(merged_html, output_json):
    sections = extract_sections_from_merged_html(merged_html)
    chunks = []
    chunk_id = 1

    for section in sections:
        for chunk in chunk_text(section["text"]):
            chunks.append({
                "chunk_id": chunk_id,
                "title": section["title"],
                "section_type": section["section_type"],
                "text": chunk
            })
            chunk_id += 1

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"[+] Saved {len(chunks)} total chunks to {output_json}")
    return chunks


# --- STEP 6: Run ---
if __name__ == "__main__":
    if not os.path.exists(MERGED_HTML):
        print(f"[!] File not found: {MERGED_HTML}")
    else:
        chunks = process_html_to_chunks(MERGED_HTML, OUTPUT_JSON)
        print("\n[Sample Output Preview]")
        for c in chunks[:3]:
            print(f"\n--- {c['title']} ({c['section_type']}) | Chunk {c['chunk_id']} ---")
            print(c['text'][:300] + ("..." if len(c['text']) > 300 else ""))
