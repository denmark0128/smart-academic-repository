import re
import unicodedata

def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r'\[\d+\]', '', text)         # remove [1], [23]
    text = re.sub(r'\s+', ' ', text)            # normalize whitespace
    text = text.strip()
    return text
    