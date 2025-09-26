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

def extract_project_description(pdf_path):
    import fitz
    import re

    doc = fitz.open(pdf_path)
    description = None

    for page in doc:
        lines = page.get_text().splitlines()
        collecting = False
        desc_lines = []

        for line in lines:
            stripped = line.strip()
            
            # Start collecting when we see Project Description:
            if not collecting and re.search(r'(?i)^project description\s*:', stripped):
                # Collect any text after the colon on the same line
                parts = re.split(r':', stripped, 1)
                if len(parts) > 1 and parts[1].strip():
                    desc_lines.append(parts[1].strip())
                collecting = True
                continue

            # Stop collecting at first empty line
            if collecting:
                if stripped == "":
                    break
                desc_lines.append(stripped)  # already stripped here

        if desc_lines:
            # Join and strip extra whitespace
            description = " ".join(desc_lines).strip()
            break

    if description:
        # Remove any multiple spaces inside text
        description = re.sub(r'\s+', ' ', description).strip()

    return description


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
        "abstract": extract_project_description(pdf_path),

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
    # Add more as needed
}

PROGRAM_MAPPING = {
    "bachelor of science in computer science": "bscs",
    "bachelor of science in information technology": "bsit",
    "bachelor of science in business administration": "bsba",
    "bachelor of secondary education": "bse",
    "bachelor of elementary education": "bee",
    "bachelor of science in accountancy": "bsa",
    "bachelor of science in civil engineering": "bsce",
    "bachelor of science in nursing": "bsn",
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
