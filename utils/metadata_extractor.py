import fitz  # PyMuPDF
import spacy
from spacy.pipeline import EntityRuler
import json
import re

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
    for line in text.splitlines():
        if line.strip().lower().startswith("bachelor"):
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


# === Run extractor on PDF ===
def extract_metadata(pdf_path):
    raw_text = extract_text_from_pdf(pdf_path)
    cleaned_text = preclean_text(raw_text)
    doc = nlp(cleaned_text)

    lines = raw_text.strip().splitlines()
    person_lines = set()
    date_lines = set()

    for ent in doc.ents:
        for line in lines:
            if ent.text in line:
                if ent.label_ == "PERSON":
                    person_lines.add(line.strip())
                elif ent.label_ == "DATE":
                    date_lines.add(line.strip())

    return {
        "title": extract_title(cleaned_text),
        "college": extract_college(cleaned_text),
        "program": extract_program(cleaned_text),
        "authors": list(person_lines),
        "year": extract_date(cleaned_text),

    }

# === Run test ===
if __name__ == "__main__":
    path_to_pdf = "SmartIR.pdf"  # Replace this
    result = extract_metadata(path_to_pdf)  
    print(result)
    print(json.dumps(result, indent=2, ensure_ascii=False))


