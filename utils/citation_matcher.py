import fitz
import re
import numpy as np
from papers.models import Paper, MatchedCitation
from pgvector.django import CosineDistance
from google import genai
from google.genai import types
from utils.semantic_search import get_model, embed_texts, GENAI_EMBEDDING_MODEL
import os
# Detect section heading
def is_reference_heading(line):
  return re.match(r"^\s*(references|bibliography|works cited)\s*$", line.strip(), re.IGNORECASE)


# Step 1: Extract references from a PDF (No changes needed here)
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
            if re.match(r"^\d+\.\s+[A-Z]", line_clean):
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


# Step 2: Parse APA-style citation (simplified - just get title)
def parse_citation_title(cite):
  """Extract title from APA citation - simplified version"""
  try:
    # Try to extract title (text after year until next period)
    title_match = re.search(r"\(\d{4}\)\.\s*(.+?)\.\s*", cite)
    if title_match:
      return title_match.group(1).strip()
    
    # Fallback: try to get any text between periods that looks like a title
    parts = cite.split('.')
    for part in parts:
      # If part has more than 3 words and no parentheses, it might be the title
      if len(part.split()) > 3 and '(' not in part:
        return part.strip()
    
    # Last resort: return first 100 chars
    return cite[:100].strip()
    
  except Exception as e:
    print(f"[Citation] Error parsing citation: {e}")
    return cite[:100].strip()

# --- HELPER FUNCTION ---
def embed_citation_title(client, title, model_name=GENAI_EMBEDDING_MODEL):
    """
    Embeds the citation title using the GenAI client.
    Uses RETRIEVAL_DOCUMENT task_type to match how paper titles are embedded
    in semantic_search.py for consistency in similarity calculations.
    """
    if not client:
        return None
    try:
        response = client.models.embed_content(
            model=model_name,
            contents=[title],
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT", output_dimensionality=768),
        )
        
        # Extract embedding from response
        if hasattr(response, 'embeddings') and response.embeddings:
            return response.embeddings[0].values
        elif hasattr(response, 'values'):
            return response.values
        else:
            print(f"[Citation] ❌ Unexpected GenAI response structure: {dir(response)}")
            return None
        
    except Exception as e:
        print(f"[Citation] ❌ Failed to generate embedding: {e}")
        import traceback
        traceback.print_exc()
        return None

# Step 3: Main function - works exactly like semantic_search but for titles
def extract_and_match_citations(paper, threshold=0.15, min_similarity=0.1):
  """
  Extract citations from a paper and match them against existing papers.
  Works just like semantic_search but queries title_embedding field.
  
  Args:
    paper: Paper model instance
    threshold: Minimum similarity score to save a match (0.0 to 1.0)
    min_similarity: Minimum similarity to even consider (optimization)
  
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
  
  # Check if we have papers with embeddings to match against
  total_papers = Paper.objects.exclude(id=paper.id).filter(
    title_embedding__isnull=False
  ).exclude(title='').count()
  
  if total_papers == 0:
    print("[Citation] No papers with embeddings in database to match against")
    return []
  
  print(f"[Citation] Matching against {total_papers} papers with title embeddings")
  
  # --- CRITICAL FIX 1: GET THE MODEL ONCE OUTSIDE THE LOOP ---
  client = get_model() # Call once to initialize/retrieve the model object
  if not client:
    print("[Citation] ❌ Failed to get GenAI client. Aborting matching.")
    return [] 
  # -------------------------------------------------------------
  
  # Match citations
  matched_citations = []
  
  for i, citation in enumerate(raw_citations):
    try:
      print(f"\n[Citation {i+1}/{len(raw_citations)}] Processing: {citation[:80]}...")
      
      # Parse citation to get title
      citation_title = parse_citation_title(citation)
      print(f"[Citation] 📝 Extracted title: '{citation_title}'")
      
      if not citation_title or len(citation_title) < 10:
        print(f"[Citation] ⚠️  Title too short, skipping")
        continue
      
      # Embed the citation title
      citation_embedding_list = embed_citation_title(client, citation_title)
      
      if citation_embedding_list is None:
        continue
      
      # Query papers by title_embedding similarity (exactly like semantic_search)
      # CosineDistance in pgvector: 0 = identical, 2 = opposite
      # So similarity = 1 - distance
      # ✅ IMPORTANT: Exclude the source paper by ID to prevent self-matching
      similar_papers = (
        Paper.objects
        .exclude(id=paper.id)
        .filter(title_embedding__isnull=False)
        .exclude(title='')  # Also exclude empty titles
        .annotate(distance=CosineDistance('title_embedding', citation_embedding_list))
        .order_by('distance')[:10]
      )
      
      if not similar_papers:
        print("[Citation] ❌ No similar papers found")
        continue
      
      # Find best match
      best_match = None
      best_score = 0.0
      
      for rank, candidate in enumerate(similar_papers, 1):
        similarity = 1 - candidate.distance 
        
        if rank <= 3:
          print(f"[Citation]   #{rank}: {candidate.title[:50]}... | Similarity: {similarity:.3f}")
        
        # Stop early if similarity drops below minimum threshold
        if similarity < min_similarity:
          break
        
        if similarity > best_score:
          best_score = similarity
          best_match = candidate
      
      # If best match exceeds threshold, save it
      if best_match and best_score >= threshold:
        print(f"[Citation] ✅ MATCHED: {best_match.title}")
        print(f"[Citation]  Score: {best_score:.3f}")
        
        # Create or update MatchedCitation
        matched_citation, created = MatchedCitation.objects.get_or_create(
          source_paper=paper,
          matched_paper=best_match,
          defaults={
            'raw_citation': citation,
            'score': best_score
          }
        )
        
        if not created and best_score > matched_citation.score:
          # Update if better score
          matched_citation.score = best_score
          matched_citation.raw_citation = citation
          matched_citation.save(update_fields=['score', 'raw_citation'])
          print(f"[Citation]  Updated with better score")
        
        matched_citations.append(matched_citation)
      else:
        if best_match:
          print(f"[Citation] ❌ Best match below threshold: {best_score:.3f} < {threshold}")
          print(f"[Citation]  '{best_match.title[:60]}...'")
        
    except Exception as e:
      print(f"[Citation] ❌ Error matching citation: {e}")
      import traceback
      traceback.print_exc()
      continue
  
  print(f"\n[Citation] ✅ Completed: {len(matched_citations)} citations matched")
  
  # Update citation counts
  try:
    for mc in matched_citations:
      if mc.matched_paper:
        citation_count = MatchedCitation.objects.filter(
          matched_paper=mc.matched_paper
        ).count()
        mc.matched_paper.citation_count_cached = citation_count
        mc.matched_paper.save(update_fields=['citation_count_cached'])
  except Exception as e:
    print(f"[Citation] ❌ Error updating citation counts: {e}")
  
  return matched_citations
