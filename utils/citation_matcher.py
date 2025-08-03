import fitz  # PyMuPDF
import re
from sentence_transformers import SentenceTransformer, util
import numpy as np
import faiss

# Load sentence transformer model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Detect section heading
def is_reference_heading(line):
    return re.match(r"^\s*(references|bibliography|works cited)\s*$", line.strip(), re.IGNORECASE)

# Step 1: Extract references from a PDF
def extract_references_from_pdf(pdf_path, max_pages_to_check=3):
    doc = fitz.open(pdf_path)
    raw_lines = []
    found_ref_section = False

    # Check only the last few pages
    pages_to_check = range(len(doc) - max_pages_to_check, len(doc))

    for page_num in pages_to_check:
        text = doc[page_num].get_text()
        lines = text.split("\n")

        for line in lines:
            line_clean = line.strip()
            lower_line = line_clean.lower()

            if not found_ref_section and is_reference_heading(line_clean):
                found_ref_section = True
                continue

            if found_ref_section:
                # Heuristic to detect end of references section
                if lower_line in ["appendix", "acknowledgements", "about the authors", "glossary"]:
                    return postprocess_reference_lines(raw_lines)
                if re.match(r"^\d+\.\s+[A-Z]", line_clean):  # new numbered section
                    return postprocess_reference_lines(raw_lines)

                if line_clean:
                    raw_lines.append(line_clean)

    return postprocess_reference_lines(raw_lines)

def postprocess_reference_lines(lines):
    citations = []
    current = ""
    for line in lines:
        if re.search(r"\(\d{4}\)", line) and current:
            citations.append(current.strip())
            current = line
        else:
            current += " " + line
    if current:
        citations.append(current.strip())
    return citations

# Step 2: Parse APA-style citation
def parse_apa_citation(cite):
    year_match = re.search(r"\((\d{4})\)", cite)
    year = year_match.group(1) if year_match else ""

    title_match = re.search(r"\)\.\s*(.+?)\.\s*[A-Z]", cite)
    title = title_match.group(1).strip() if title_match else ""

    author_part = cite.split("(")[0]
    authors = [name.strip().split(",")[0] for name in author_part.split("&")[0].split(",") if name.strip()]

    return {
        "title": title,
        "authors": authors,
        "year": year
    }

# Step 3: Compare citation with known papers
def compare_citation_with_known(parsed, known_papers):
    parsed_embed = model.encode(parsed['title'], convert_to_tensor=True)

    best_match = None
    best_score = 0.0

    for paper in known_papers:
        paper_embed = model.encode(paper['title'], convert_to_tensor=True)
        title_sim = float(util.pytorch_cos_sim(parsed_embed, paper_embed)[0][0])

        parsed_authors = set(a.lower() for a in parsed['authors'])
        paper_authors = set(a.lower() for a in paper['authors'])
        author_overlap = len(parsed_authors.intersection(paper_authors)) / max(len(paper_authors), 1)

        year_match = 1.0 if parsed['year'] == paper['year'] else 0.0

        final_score = (0.7 * title_sim) + (0.2 * author_overlap) + (0.1 * year_match)

        if final_score > best_score:
            best_score = final_score
            best_match = paper

    return best_match, best_score

# Step 4: Run the system
def run_reference_matching(pdf_path, known_papers, model, threshold=0.75, return_matches=False):
    refs = extract_references_from_pdf(pdf_path)

    if not refs:
        print("⚠ No references found.")
        return [] if return_matches else None

    dim = model.get_sentence_embedding_dimension()
    index = faiss.IndexFlatIP(dim)
    title_embeddings = []
    metadata = []

    for paper in known_papers:
        emb = paper['embedding']
        emb_np = emb.cpu().numpy()
        norm = np.linalg.norm(emb_np)
        if norm > 0:
            emb_np = emb_np / norm
        title_embeddings.append(emb_np)
        metadata.append(paper)

    index.add(np.array(title_embeddings))

    matched_results = []

    for citation in refs:
        print(f"\n📚 Raw citation: {citation}")
        parsed = parse_apa_citation(citation)

        if not parsed['title']:
            print("❌ Could not parse title.")
            continue

        parsed_emb = model.encode(parsed['title'], convert_to_tensor=False)
        parsed_emb = parsed_emb / np.linalg.norm(parsed_emb)
        parsed_emb = np.expand_dims(parsed_emb, axis=0)

        D, I = index.search(parsed_emb, 1)
        match_idx = I[0][0]
        similarity = float(D[0][0])

        matched = metadata[match_idx]
        parsed_authors = set(a.lower() for a in parsed['authors'])
        paper_authors = set(a.lower() for a in matched['authors'])
        author_overlap = len(parsed_authors.intersection(paper_authors)) / max(len(paper_authors), 1)

        year_match = 1.0 if parsed['year'] == matched['year'] else 0.0

        final_score = (0.7 * similarity) + (0.2 * author_overlap) + (0.1 * year_match)

        if final_score >= threshold:
            print(f"✅ Matched: {matched['title']}")
            print(f"🔢 Score: {final_score:.3f}")

            if return_matches:
                matched_results.append({
                    "raw_citation": citation,
                    "score": final_score,
                    "matched_id": matched["id"]
                })
        else:
            print("❌ No strong match.")
            print(f"🔢 Score: {final_score:.3f}")

    return matched_results if return_matches else None

