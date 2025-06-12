import spacy
import re

nlp = spacy.load("en_core_web_sm")

def clean_tag(tag):
    tag = tag.strip().replace("\n", " ")
    tag = re.sub(r'\s+', ' ', tag)  # Normalize spaces
    tag = tag.lower()
    tag = re.sub(r'^(the|a|an)\s+', '', tag)

    stopwords = {
        "this paper", "our approach", "application", "approach", "paper"
    }

    if len(tag) <= 2 or tag in stopwords:
        return None

    if len(tag.split()) > 6:
        return None

    return tag

def extract_tags(text):
    doc = nlp(text)
    tags = set()

    for chunk in doc.noun_chunks:
        cleaned = clean_tag(chunk.text)
        if cleaned:
            if " and " in cleaned:
                parts = cleaned.split(" and ")
                for part in parts:
                    if len(part.split()) > 1:
                        tags.add(part.strip())
            else:
                tags.add(cleaned)

    for ent in doc.ents:
        cleaned = clean_tag(ent.text)
        if cleaned:
            tags.add(cleaned)

    return sorted(tags)
