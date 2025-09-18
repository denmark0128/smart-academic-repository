# Project Change Log & Feature Notes

This notepad documents all major changes, features, and improvements made to the thesis paper repository project. Continue to add new entries as you make further changes.

---

## 1. Semantic Search Improvements
- Implemented semantic search using SentenceTransformer and FAISS.
- Added logic to return only the highest-scoring chunk per paper title in search results.
- Added fallback to keyword search (case-insensitive, across text, title, and author) if semantic search returns no results.
- Switched priority: keyword search is now used first, then semantic search as fallback.
- Search result now include tags (July 20)

## 2. Tag Extraction
- Tag extraction uses a bank of words and now includes general academic topics (e.g., computer science, medicine, biology, etc.).
- Added a management command to re-extract and update tags for all existing papers.
- Tag extraction now includes the title (July 20)

## 3. UI/UX Enhancements
- Home and paper list pages restyled for academic, elegant look using Tailwind CSS and Alpine.js.
- Paper list: search bar, upload button, and table improved for clarity and usability.
- Paper list: chunk/snippet preview is truncated to 180 characters, expandable on row click.
- Tags are displayed for each paper in the list.
- Introduction chunk logic was added and later removed per user request (no introduction chunk in current version).
- Score and Page columns in the paper list table are commented out (hidden by default).
- Paper list: changed the ui from table to whole (June 18)
- Navbar: changed the style to white bg and black text. (June 18)

## 4. Management & Maintenance
- Provided instructions for running management commands to update tags.
- Provided guidance for reverting changes and best practices for server restarts after code edits.

## 5. Profile Page
- Added profile page skeleton (June 18)
- Saving papers wip  

## 6. Citation Matching System (August 3)
- Implemented citation matching using the same SentenceTransformer model (`all-MiniLM-L6-v2`) for title similarity.
- Combined title similarity, author surname overlap, and year match to calculate a final similarity score.
- Matching formula:  
  `Final Score = 0.7 * Title Similarity + 0.2 * Author Overlap + 0.1 * Year Match`  
- Added citation match threshold (≥ 0.75) to minimize false positives.
- Extracted citations now attempt to auto-match against existing theses in the repository.
- Each paper now shows:
  - References it cites (Matched Citations)
  - Other papers that cite it (Cited By)

## Metadata Extraction
- Metadata extraction from title pages using heuristic and spacy EntityRuler

## 7. Paper Model Author Refactor (August 3)
- Changed `authors` field in the `Paper` model to a many-to-many relationship with a new `Author` model.
- Added Select2 tagging widget in the admin and form for easier author selection and creation.
- Supports multiple authors with autocomplete and manual entry.

## 9. Staff Page
- added staff page with dashboard


_Created at: June 17, 2025_  
_Last updated: August 4, 2025_
