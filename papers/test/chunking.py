def chunk_text(text, max_tokens=500):
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]  # Split by single newline, strip blanks
    chunks = []
    current_chunk = []

    for para in paragraphs:
        current_len = sum(len(p.split()) for p in current_chunk)
        para_len = len(para.split())

        if current_len + para_len <= max_tokens:
            current_chunk.append(para)
        else:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            current_chunk = [para]

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


# Step 1: Read the file you created earlier
with open("output.txt", "r", encoding="utf-8") as f:
    full_text = f.read()

chunks = chunk_text(full_text)

print(f"✅ Chunked into {len(chunks)} parts.")
for i, chunk in enumerate(chunks):
    with open(f"chunk_{i+1}.txt", "w", encoding="utf-8") as f:
        f.write(chunk)

