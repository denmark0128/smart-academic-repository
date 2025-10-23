import os
import json
from bs4 import BeautifulSoup
from django.conf import settings

def extract_sections_from_merged_html(merged_path):
    """Extract relevant sections from merged.html inside CHM folder."""
    with open(merged_path, "r", encoding="utf-8", errors="ignore") as f:
        soup = BeautifulSoup(f, "html.parser")

    content_div = soup.find("div", id="content")
    if not content_div:
        raise ValueError("No <div id='content'> found in merged.html")

    sections = []
    current_title = None
    current_text = []

    for elem in content_div.children:
        if elem.name == "h2":  # detect new section
            if current_title and current_text:
                if is_valid_section(current_title):
                    sections.append({
                        "title": current_title.strip(),
                        "text": " ".join(current_text).strip()
                    })
            current_title = elem.get_text().strip()
            current_text = []
        elif elem.name:
            current_text.append(elem.get_text(separator=" ", strip=True))

    if current_title and current_text and is_valid_section(current_title):
        sections.append({
            "title": current_title.strip(),
            "text": " ".join(current_text).strip()
        })

    return sections


def is_valid_section(title):
    """Keep Abstract and Chapters I–V only."""
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


def chunk_text(text, max_chars=1000):
    """Split text into 1000-character chunks (sentence-aware)."""
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


def process_html_to_chunks(merged_html_path, paper_title):
    """
    Process merged.html into JSON chunks for storage or embedding.
    Returns a Python list of chunks.
    """
    sections = extract_sections_from_merged_html(merged_html_path)
    chunks = []
    chunk_id = 1

    for section in sections:
        for chunk in chunk_text(section["text"]):
            chunks.append({
                "chunk_id": chunk_id,
                "title": section["title"],
                "text": chunk
            })
            chunk_id += 1

    # Save to media folder, next to CHM
    output_dir = os.path.join(settings.MEDIA_ROOT, f"chm_{paper_title}")
    os.makedirs(output_dir, exist_ok=True)
    output_json_path = os.path.join(output_dir, "merged_chunks.json")

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    return chunks
