#metadata_extractor.py
import fitz  # PyMuPDF
import os
from google import genai
from dotenv import load_dotenv
import spacy
from spacy.pipeline import EntityRuler
import json
from django.conf import settings
import re

# --- Environment Setup ---
BASE_DIR = settings.BASE_DIR
load_dotenv(BASE_DIR / ".env")
api_key = os.getenv("GEMINI_API_KEY")




# === PDF text extractor ===
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    if len(doc) > 0:
        return doc[0].get_text()
    return ""

# === Pre-clean OCR typos ===
def preclean_text(text):
    # Fix OCR errors
    text = text.replace(" 0.", " O.")

    # Split, strip, and keep only non-empty lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Join lines with single newline (no empty lines)
    return "\n".join(lines)

def extract_metadata_with_llm(text):
    prompt = f"""
    Extract metadata from the text of an academic paper.
    Respond ONLY with a valid JSON object.
    Include any of these keys if found: "title", "authors", "year" (default to 2025 if no date is found), "college", "program", "abstract".
    Text:
    {text}
    """

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemma-3-27b-it",
        contents=prompt,
    )

    response_text = response.text.strip()
    print("[LLM RAW RESPONSE]", response_text)

    # Try to capture JSON inside ```json ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    json_to_parse = match.group(1) if match else response_text

    try:
        metadata = json.loads(json_to_parse)
        print("[LLM INFO] Successfully parsed JSON.")
    except json.JSONDecodeError:
        print("[LLM WARNING] Invalid JSON, returning empty dict.")
        metadata = {}

    return metadata



def extract_date(text):
    return re.findall(r'\b(20\d{2})\b', text)

def extract_college(text):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("college"):
            # Remove trailing "of" if it's the last word
            if stripped.lower().endswith(" of"):
                stripped = " ".join(stripped.split()[:-1])
            return stripped
    return None

def extract_program(text):
    prefixes = ["bachelor", "degree"]
    for line in text.splitlines():
        stripped_line = line.strip().lower()
        if any(stripped_line.startswith(prefix) for prefix in prefixes):
            return line.strip()
    return None


# === Title extractor ===
def extract_title(text):
    lines = text.strip().splitlines()
    cue_phrases = [
        "a thesis proposal",
        "a case study proposal",
        "a research paper presented",
        "a capstone project",
        "a thesis presented",
        "a research study presented",
        "an undergraduate thesis",
        "a graduate thesis",
        "a dissertation",
        "a final project",

    ]
    for i, line in enumerate(lines):
        if any(cue in line.lower() for cue in cue_phrases):
            title_lines = []
            j = i - 1
            while j >= 0 and lines[j].strip():
                title_lines.insert(0, lines[j].strip())
                j -= 1
            return " ".join(title_lines)
    return None

# === spaCy setup ===
nlp = spacy.blank("en")
ruler = nlp.add_pipe("entity_ruler")
patterns = [
    {
        "label": "PERSON",
        "pattern": [
            {"IS_TITLE": True}, {"TEXT": ","},
            {"IS_TITLE": True},
            {"IS_TITLE": True, "OP": "*"},
            {"IS_ALPHA": True, "OP": "?"}, {"TEXT": ".", "OP": "?"}
        ]
    },
]
ruler.add_patterns(patterns)

def extract_project_description(pdf_path):
    import fitz
    import re

    doc = fitz.open(pdf_path)
    collecting = False
    desc_lines = []

    for page in doc:
        lines = page.get_text().splitlines()
        for line in lines:
            stripped = line.strip()

            # Start collecting when "Project Description:" appears
            if not collecting and re.search(r'(?i)^project description\s*:', stripped):
                parts = re.split(r':', stripped, 1)
                if len(parts) > 1 and parts[1].strip():
                    desc_lines.append(parts[1].strip())
                collecting = True
                continue

            
            # Stop if we detect the start of a new chapter (only after collecting)
            if collecting and re.search(r'(?i)^\s*chapter\s+\d+', stripped):
                collecting = False
                break

            # Stop only if completely empty line *and* we've collected enough text already
            if collecting and stripped == "":
                # check if the next lines are just spacing or still part of description
                continue

            # Add lines while collecting
            if collecting:
                desc_lines.append(stripped)

        if not collecting and desc_lines:
            # we already finished collecting and broke from the inner loop
            break

    # Join and clean up
    if desc_lines:
        description = re.sub(r'\s+', ' ', " ".join(desc_lines)).strip()
        return description

    return None


# === Run extractor on PDF ===
def extract_metadata(pdf_path):
    # 1. Extract text
    raw_text = extract_text_from_pdf(pdf_path)
    cleaned_text = preclean_text(raw_text)

    # 2. Try LLM extraction
    metadata = {}
    try:
        metadata = extract_metadata_with_llm(cleaned_text)
    except Exception as e:
        print(f"[LLM ERROR] {e}")
        # fallback to old extraction if LLM fails
        metadata = {}

    # 3. Fallback to old methods if any key is missing or empty
    title = metadata.get("title") or extract_title(cleaned_text)
    college = metadata.get("college") or extract_college(cleaned_text)
    program = metadata.get("program") or extract_program(cleaned_text)
    authors = metadata.get("authors") or []
    
    # If LLM didn't give authors, fallback to spaCy
    if not authors:
        doc = nlp(cleaned_text)
        lines = raw_text.strip().splitlines()
        person_lines = set()
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                for line in lines:
                    if ent.text in line:
                        person_lines.add(line.strip())
        authors = list(person_lines)
    
    year = metadata.get("year") or extract_date(cleaned_text)
    abstract = metadata.get("abstract") or extract_project_description(pdf_path)  # keep existing abstract extraction

    return {
        "title": title,
        "college": college,
        "program": program,
        "authors": authors,
        "year": year,
        "abstract": abstract,
    }

# === Run test ===
if __name__ == "__main__":
    path_to_pdf = "SmartIR.pdf"  # Replace this
    result = extract_metadata(path_to_pdf)  
    print(result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


# metadata_utils.py

COLLEGE_MAPPING = {
    "college of computer studies": "ccs",
    "college of business and accountancy": "cba",
    "college of arts and sciences": "cas",
    "college of engineering": "coe",
    "college of education": "ced",
    "college of nursing": "con",
    "college of international hospitality management": "cihm",
    # Add more as needed
}

PROGRAM_MAPPING = {
    "bachelor of science in computer science": "bscs",
    "bachelor of science in information technology": "bsit",
    "bachelor of science in business administration": "bsba",
    "bachelor of secondary education": "bse",
    "bachelor of science in accountancy": "bsa",
    "bachelor of science in civil engineering": "bsce",
    "bachelor of science in nursing": "bsn",
    "bachelor of science in hospitality management": 'bshm'
    # Add more as needed
}

def normalize_college(text):
    if not text:
        return None
    text = text.lower().strip()
    return COLLEGE_MAPPING.get(text, None)

def normalize_program(text):
    if not text:
        return None
    text = text.lower().strip()
    return PROGRAM_MAPPING.get(text, None)
