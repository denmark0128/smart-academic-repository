# views/task.py
'''
import traceback
from celery import chord, group, shared_task
from django.conf import settings
from papers.models import Paper, MatchedCitation
from utils.tagging import extract_tags, get_embedding_model
from utils.semantic_search import index_paper
from utils.citation_matcher import extract_and_match_citations
from utils.summarize import generate_summary_with_api

# -----------------------------------------------------------------------------
# MAIN COORDINATOR TASK
# -----------------------------------------------------------------------------

@shared_task(time_limit=7200)
def process_paper_task(paper_id):
    """
    Background task to process uploaded paper.
    Runs HEAVY processing steps only (embeddings, indexing, tags, summary, citations).
    Metadata extraction already completed in the view.
    """
    paper = None 
    try:
        paper = Paper.objects.get(id=paper_id)
        
        # --- NEW: SET STATUS TO "PROCESSING" ---
        # This tells the front-end the task has started
        paper.status = "processing"
        paper.save(update_fields=["status"])
        print(f"[Task] Processing paper ID: {paper_id}")
        
        # --- STEP 1: Generate Embeddings ---
        try:
            print("[Task] Generating embeddings...")
            model = get_embedding_model()
            fields_to_update = []

            if paper.title:
                try:
                    paper.title_embedding = model.encode(paper.title, convert_to_numpy=True)
                    fields_to_update.append("title_embedding")
                    print("[Task] Generated title embedding")
                except Exception as e:
                    print(f"[Task] Title Embedding Error: {e}")

            if paper.abstract:
                try:
                    paper.abstract_embedding = model.encode(paper.abstract, convert_to_numpy=True)
                    fields_to_update.append("abstract_embedding")
                    print("[Task] Generated abstract embedding")
                except Exception as e:
                    print(f"[Task] Abstract Embedding Error: {e}")

            if fields_to_update:
                paper.save(update_fields=fields_to_update)
                print(f"[Task] Saved embeddings: {fields_to_update}")
        except Exception as e:
            print(f"[Task] Embedding Error: {e}")

        # --- STEP 2: Semantic Search Indexing ---
        try:
            print("[Task] Indexing paper for semantic search")
            index_paper(paper)
            paper.is_indexed = True
            paper.save(update_fields=["is_indexed"])
            print("[Task] Paper indexed successfully")
        except Exception as e:
            print(f"[Task] Indexing Error: {e}")

        # --- STEP 3: Tag Extraction ---
        try:
            print("[Task] Extracting tags...")
            embedding_for_tagging = None
            
            if paper.abstract_embedding is not None:
                embedding_for_tagging = paper.abstract_embedding
                print("[Task] Using abstract_embedding for tags")
            elif paper.title_embedding is not None:
                embedding_for_tagging = paper.title_embedding
                print("[Task] Using title_embedding for tags")

            if embedding_for_tagging is not None:
                tags_with_scores = extract_tags(doc_emb=embedding_for_tagging)
                if tags_with_scores:
                    tag_names = [t['name'] for t in tags_with_scores]
                    paper.tags = tag_names
                    paper.save(update_fields=["tags"])
                    print(f"[Task] Tags saved: {tag_names}")
            else:
                print("[Task] No embeddings available for tagging")
        except Exception as e:
            print(f"[Task] Tag Extraction Error: {e}")

        # --- STEP 4: Summary Generation ---
        try:
            print("[Task] Generating summary...")
            summary = generate_summary_with_api(paper)
            if summary:
                paper.summary = summary
                paper.save(update_fields=["summary"])
                print("[Task] Summary generated and saved")
            else:
                print("[Task] No summary generated")
        except Exception as e:
            print(f"[Task] Summary Generation Error: {e}")

        # --- STEP 5: Citation Extraction ---
        try:
            print("[Task] Extracting and matching citations")
            matched_citations = extract_and_match_citations(
                paper=paper,
                threshold=0.75,
                top_k=5
            )
            
            paper.matched_count_cached = len(matched_citations)
            
            paper.citation_count_cached = MatchedCitation.objects.filter(
                matched_paper=paper
            ).count()
            
            paper.save(update_fields=["matched_count_cached", "citation_count_cached"])
            print(f"[Task] Found {len(matched_citations)} citations from this paper")
            print(f"[Task] This paper is cited {paper.citation_count_cached} times")
            
        except Exception as e:
            print(f"[Task] Citation Matching Error: {e}")
            traceback.print_exc()

        # --- STEP 6: Mark Complete ---
        paper.status = "complete" # <--- This is the "success" status
        paper.save(update_fields=["status"])
        print(f"[Task] Processing complete for paper ID: {paper_id}")
        
        return True

    except Paper.DoesNotExist:
        print(f"[Task] Paper with ID {paper_id} not found")
        return False
        
    except Exception as e:
        print(f"[Task] Fatal error processing paper {paper_id}: {e}")
        traceback.print_exc()
        
        # --- NEW: MARK PAPER AS FAILED ---
        # This is the crucial error handler
        if paper: # Check if paper object was fetched successfully
            try:
                paper.status = "failed"
                paper.save(update_fields=["status"])
            except Exception as e_save:
                print(f"[Task] CRITICAL: Could not even save failed status. {e_save}")
        
        return False

        '''