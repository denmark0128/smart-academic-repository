#citation_matcher.py
import fitz  # PyMuPDF
import re
import numpy as np
from papers.models import Paper, MatchedCitation
# ✅ CHANGED: Import GenAI client instead of sentence_transformers model
from utils.semantic_search import get_model, GENAI_EMBEDDING_MODEL
from google.genai import types
from django.db.models import F
from pgvector.django import CosineDistance
import os


# Detect section heading
def is_reference_heading(line):
    return re.match(r"^\s*(references|bibliography|works cited)\s*$", line.strip(), re.IGNORECASE)


# Step 1: Extract references from a PDF
def extract_references_from_pdf(pdf_path, max_pages_to_check=3):
    """Extract reference citations from the last few pages of a PDF"""
    try:
        if not os.path.exists(pdf_path):
            print(f"[Citation] PDF not found: {pdf_path}")
            return []
        
        doc = fitz.open(pdf_path)
        raw_lines = []
        found_ref_section = False

        # Check only the last few pages
        start_page = max(0, len(doc) - max_pages_to_check)
        pages_to_check = range(start_page, len(doc))

        for page_num in pages_to_check:
            try:
                text = doc[page_num].get_text()
                lines = text.split("\n")

                for line in lines:
                    line_clean = line.strip()
                    lower_line = line_clean.lower()

                    if not found_ref_section and is_reference_heading(line_clean):
                        found_ref_section = True
                        print(f"[Citation] Found references section on page {page_num + 1}")
                        continue

                    if found_ref_section:
                        # Heuristic to detect end of references section
                        if lower_line in ["appendix", "acknowledgements", "about the authors", "glossary"]:
                            doc.close()
                            return postprocess_reference_lines(raw_lines)
                        if re.match(r"^\d+\.\s+[A-Z]", line_clean):  # new numbered section
                            doc.close()
                            return postprocess_reference_lines(raw_lines)

                        if line_clean:
                            raw_lines.append(line_clean)
            except Exception as e:
                print(f"[Citation] Error reading page {page_num}: {e}")
                continue

        doc.close()
        return postprocess_reference_lines(raw_lines)
    
    except Exception as e:
        print(f"[Citation] Error opening PDF: {e}")
        return []


def postprocess_reference_lines(lines):
    """Merge multi-line citations into single entries"""
    citations = []
    current = ""
    
    for line in lines:
        # Detect start of new citation (usually has a year in parentheses)
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
    """Extract title, authors, and year from APA citation"""
    try:
        year_match = re.search(r"\((\d{4})\)", cite)
        year = year_match.group(1) if year_match else ""

        # Try to extract title (text between year and next period/capital letter)
        title_match = re.search(r"\)\.\s*(.+?)\.\s*[A-Z]", cite)
        if not title_match:
            # Fallback: get text after year until period
            title_match = re.search(r"\)\.\s*(.+?)\.", cite)
        
        title = title_match.group(1).strip() if title_match else ""

        # Extract authors (text before first parenthesis)
        author_part = cite.split("(")[0] if "(" in cite else cite
        authors = []
        
        # Split by common author separators
        for name in re.split(r"[,&]", author_part):
            name = name.strip()
            if name:
                # Get last name only (text before comma)
                last_name = name.split(",")[0].strip()
                if last_name:
                    authors.append(last_name)

        return {
            "title": title,
            "authors": authors[:3],  # Limit to first 3 authors
            "year": year
        }
    except Exception as e:
        print(f"[Citation] Error parsing citation: {e}")
        return {"title": "", "authors": [], "year": ""}


# ✅ NEW: Helper function to generate embeddings using GenAI
def generate_embedding(client, text):
    """Generate embedding for a single text using GenAI"""
    try:
        response = client.models.embed_content(
            model=GENAI_EMBEDDING_MODEL,
            contents=[text],
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=768)
        )
        
        # Access embedding based on response structure
        if hasattr(response, 'embeddings'):
            embedding = np.array(response.embeddings[0].values, dtype=np.float32)
        elif hasattr(response, 'values'):
            embedding = np.array(response.values, dtype=np.float32)
        else:
            print(f"[Citation] ❌ Unexpected response structure: {dir(response)}")
            return None
        
        # Normalize the embedding
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        return embedding
        
    except Exception as e:
        print(f"[Citation] Error generating embedding: {e}")
        import traceback
        traceback.print_exc()
        return None


# Step 3: Main function to extract and match citations using pgvector
def extract_and_match_citations(paper, threshold=0.75, top_k=5):
    """
    Extract citations from a paper and match them against existing papers using pgvector.
    
    Args:
        paper: Paper model instance
        threshold: Minimum similarity score to consider a match (0.0 to 1.0)
        top_k: Number of top candidates to consider for matching
    
    Returns:
        List of MatchedCitation objects that were created
    """
    print(f"[Citation] Starting citation extraction for paper ID: {paper.id}")
    
    # Get file path
    file_path = paper.file.path
    ext = os.path.splitext(file_path)[1].lower()
    
    # Currently only support PDF
    if ext != ".pdf":
        print(f"[Citation] Skipping non-PDF file: {ext}")
        return []
    
    # Extract raw citations from PDF
    raw_citations = extract_references_from_pdf(file_path)
    
    if not raw_citations:
        print("[Citation] No references found in PDF")
        return []
    
    print(f"[Citation] Found {len(raw_citations)} raw citations")
    
    # ✅ CHANGED: Get GenAI client instead of embedding model
    try:
        client = get_model()
        if not client:
            print("[Citation] Error: GenAI client not available")
            return []
    except Exception as e:
        print(f"[Citation] Error loading GenAI client: {e}")
        return []
    
    # Check if we have papers with embeddings to match against
    papers_with_embeddings = Paper.objects.exclude(id=paper.id).filter(
        title_embedding__isnull=False
    ).exclude(title='')
    
    if not papers_with_embeddings.exists():
        print("[Citation] No papers with embeddings in database to match against")
        return []
    
    print(f"[Citation] Matching against {papers_with_embeddings.count()} papers with embeddings")
    
    # Match citations
    matched_citations = []
    
    for i, citation in enumerate(raw_citations):
        try:
            print(f"\n[Citation {i+1}/{len(raw_citations)}] Processing: {citation[:100]}...")
            
            # Parse citation
            parsed = parse_apa_citation(citation)
            
            if not parsed['title']:
                parsed['title'] = citation
                print(f"[Citation] Using full text as fallback: {citation[:80]}")
            
            # ✅ CHANGED: Generate embedding using GenAI
            citation_embedding = generate_embedding(client, parsed['title'])
            
            if citation_embedding is None:
                print("[Citation] Failed to generate embedding, skipping")
                continue
            
            # Use pgvector to find top_k most similar papers by title
            # CosineDistance: lower is better (0 = identical, 2 = opposite)
            similar_papers = Paper.objects.exclude(id=paper.id).filter(
                title_embedding__isnull=False
            ).annotate(
                distance=CosineDistance('title_embedding', citation_embedding)
            ).order_by('distance')[:top_k]
            
            if not similar_papers:
                print("[Citation] No similar papers found")
                continue
            
            # Evaluate each candidate
            best_match = None
            best_score = 0.0
            
            for candidate in similar_papers:
                title_similarity = 1 - candidate.distance
                
                # Calculate author overlap
                parsed_authors = set(a.lower() for a in parsed['authors'])
                paper_authors = set(a.lower() for a in (candidate.authors or []))
                
                if paper_authors:
                    author_overlap = len(parsed_authors.intersection(paper_authors)) / len(paper_authors)
                else:
                    author_overlap = 0.0
                
                # Calculate year match
                candidate_year = str(candidate.year) if candidate.year else ""
                year_match = 1.0 if parsed['year'] == candidate_year else 0.0
                
                # Calculate final weighted score
                final_score = (0.7 * title_similarity) + (0.2 * author_overlap) + (0.1 * year_match)
                
                print(f"[Citation]   Candidate: {candidate.title[:50]}...")
                print(f"[Citation]   Scores - Title: {title_similarity:.3f}, Author: {author_overlap:.3f}, Year: {year_match:.3f}, Final: {final_score:.3f}")
                
                if final_score > best_score:
                    best_score = final_score
                    best_match = candidate
            
            # If best match exceeds threshold, create citation record
            if best_match and best_score >= threshold:
                print(f"[Citation] ✅ Matched: {best_match.title}")
                print(f"[Citation] Final Score: {best_score:.3f}")
                
                # Create or update MatchedCitation
                matched_citation, created = MatchedCitation.objects.get_or_create(
                    source_paper=paper,
                    matched_paper=best_match,
                    defaults={
                        'raw_citation': citation,
                        'score': best_score
                    }
                )
                
                if not created:
                    # Update if better score
                    if best_score > matched_citation.score:
                        matched_citation.score = best_score
                        matched_citation.raw_citation = citation
                        matched_citation.save()
                        print(f"[Citation] Updated existing match with better score")
                
                matched_citations.append(matched_citation)
            else:
                print(f"[Citation] ❌ Low score: {best_score:.3f}")
                
        except Exception as e:
            print(f"[Citation] Error matching citation: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n[Citation] Completed: {len(matched_citations)} citations matched")
    
    # Update citation counts
    try:
        # Update citation count for papers that were cited
        for mc in matched_citations:
            if mc.matched_paper:
                citation_count = MatchedCitation.objects.filter(
                    matched_paper=mc.matched_paper
                ).count()
                mc.matched_paper.citation_count_cached = citation_count
                mc.matched_paper.save(update_fields=['citation_count_cached'])
    except Exception as e:
        print(f"[Citation] Error updating citation counts: {e}")
    
    return matched_citations