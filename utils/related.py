from .semantic_search import load_index, load_metadata, save_index, save_metadata, get_model
import faiss

def find_related_papers(paper_title, top_k=5, min_score=0.1):
    print(f"Searching related papers for: {paper_title}")

    index = load_index()
    metadata = load_metadata()

    # Normalize titles for matching
    paper_title_norm = paper_title.strip().lower()
    paper_chunks = [m['text'] for m in metadata if m['title'].strip().lower() == paper_title_norm]
    print(f"Found {len(paper_chunks)} chunks for paper titled '{paper_title}'")

    if not paper_chunks:
        print("No chunks found for this paper title in metadata.")
        return []

    paper_text = " ".join(paper_chunks)
    model = get_model()
    query_emb = model.encode([paper_text], convert_to_numpy=True)
    faiss.normalize_L2(query_emb)

    D, I = index.search(query_emb, top_k * 10)
    print(f"Search scores: {D[0]}")
    print(f"Search indices: {I[0]}")

    related = {}
    for score, idx in zip(D[0], I[0]):
        if idx >= len(metadata):
            print(f"Skipping index {idx} - out of metadata range")
            continue
        if score < min_score:
            print(f"Skipping index {idx} - score {score} below min_score {min_score}")
            continue
        meta = metadata[idx]
        related_title_norm = meta['title'].strip().lower()
        if related_title_norm == paper_title_norm:
            continue  # skip same paper
        if related_title_norm not in related or score > related[related_title_norm]['score']:
            related[related_title_norm] = {
                'title': meta['title'],
                'authors': meta.get('authors', []),
                'score': float(score),
            }
        if len(related) >= top_k:
            break

    results = sorted(related.values(), key=lambda x: x['score'], reverse=True)
    print(f"Found {len(results)} related papers.")
    return results

def build_title_index(papers):
    titles = [p['title'] for p in papers]
    model = get_model()
    embeddings = model.encode(titles, show_progress_bar=True, convert_to_numpy=True)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)
    save_index(index)
    # Save metadata per paper, no chunks
    metadata = [{'title': p['title'], 'authors': p['authors']} for p in papers]
    save_metadata(metadata)
