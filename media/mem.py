import os
import faiss

index = faiss.read_index("media/indices/paragraphs.index")
print("Number of vectors in index:", index.ntotal)
index_path = "media/indices/paragraphs.index"
size_bytes = os.path.getsize(index_path)
print(f"Index file size: {size_bytes / (1024*1024):.2f} MB")