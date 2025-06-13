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

    # Extract noun chunks and clean
    for chunk in doc.noun_chunks:
        cleaned = clean_tag(chunk.text)
        if cleaned:
            # Handle "X and Y" phrases like "dropout and augmentation"
            if " and " in cleaned:
                parts = cleaned.split(" and ")
                for part in parts:
                    if len(part.split()) > 1:
                        tags.add(part.strip())
            else:
                tags.add(cleaned)

    # Add named entities
    for ent in doc.ents:
        cleaned = clean_tag(ent.text)
        if cleaned:
            tags.add(cleaned)

    return sorted(tags)

# Example paragraph
paragraph = """
This paper explores the application of convolutional neural networks (CNNs) 
for image classification tasks. Using the CIFAR-10 dataset, we trained a deep 
learning model with dropout regularization and data augmentation to improve 
accuracy. Our approach outperformed traditional machine learning algorithms.
"""

# Extract tags
tags = extract_tags(paragraph)
print("Extracted Tags:")
print(tags)
