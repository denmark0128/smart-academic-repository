from django.core.management.base import BaseCommand
from papers.models import Paper, MatchedCitation
from utils.citation_matcher import run_reference_matching


class Command(BaseCommand):
    help = "Scans all papers, extracts citations, matches them via FAISS, and stores the matches."

    def handle(self, *args, **kwargs):
        model = SentenceTransformer("all-MiniLM-L6-v2")
        all_papers = Paper.objects.all()

        if not all_papers.exists():
            self.stdout.write(self.style.ERROR("No papers found."))
            return

        self.stdout.write(self.style.NOTICE(f"📄 Scanning {all_papers.count()} papers..."))

        # Precompute embeddings
        precomputed = {}
        for paper in all_papers:
            if not paper.title:
                continue
            emb = model.encode(paper.title, convert_to_tensor=True)
            precomputed[paper.id] = {
                "id": paper.id,  # Add ID for reference
                "title": paper.title,
                "authors": paper.authors,
                "year": str(paper.year) if paper.year else "",
                "embedding": emb
            }

        for paper in all_papers:
            if not paper.file:
                self.stdout.write(self.style.WARNING(f"⚠ Skipping '{paper.title}' (no file)"))
                continue

            self.stdout.write(self.style.SUCCESS(f"\n📄 Processing: {paper.title}"))

            try:
                pdf_path = paper.file.path
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Could not access file: {e}"))
                continue

            known = [v for k, v in precomputed.items() if k != paper.id]

            if not known:
                self.stdout.write(self.style.WARNING("⚠ No other papers to match against."))
                continue

            matches = run_reference_matching(pdf_path, known, model=model, return_matches=True)

            for match in matches:
                matched_id = match["matched_id"]
                matched_paper = Paper.objects.filter(id=matched_id).first()

                if not matched_paper:
                    continue

                MatchedCitation.objects.update_or_create(
                    source_paper=paper,
                    matched_paper=matched_paper,
                    raw_citation=match["raw_citation"],
                    defaults={"score": match["score"]}
                )
