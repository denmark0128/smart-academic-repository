# Project Change Log & Feature Notes

This notepad documents all major changes, features, and improvements made to the thesis paper repository project. Continue to add new entries as you make further changes.

---

## 1. Semantic Search Improvements
- Implemented semantic search using SentenceTransformer and FAISS.
- Added logic to return only the highest-scoring chunk per paper title in search results.
- Added fallback to keyword search (case-insensitive, across text, title, and author) if semantic search returns no results.
- Switched priority: keyword search is now used first, then semantic search as fallback.

## 2. Tag Extraction
- Tag extraction uses a bank of words and now includes general academic topics (e.g., computer science, medicine, biology, etc.).
- Added a management command to re-extract and update tags for all existing papers.

## 3. UI/UX Enhancements
- Home and paper list pages restyled for academic, elegant look using Tailwind CSS and Alpine.js.
- Paper list: search bar, upload button, and table improved for clarity and usability.
- Paper list: chunk/snippet preview is truncated to 180 characters, expandable on row click.
- Tags are displayed for each paper in the list.
- Introduction chunk logic was added and later removed per user request (no introduction chunk in current version).
- Score and Page columns in the paper list table are commented out (hidden by default).

## 4. Management & Maintenance
- Provided instructions for running management commands to update tags.
- Provided guidance for reverting changes and best practices for server restarts after code edits.

---

## How to Use This Notepad
- Add a new section for each new feature, bugfix, or major edit.
- Note the date and a short summary of what was changed or added.
- Use this as a running log to continue your work in future sessions or new chats.

---

_Last updated: June 17, 2025_
