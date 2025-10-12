from django.core.management.base import BaseCommand
from papers.models import Paper, PaperChunk
from utils.semantic_search import index_paper  # <-- your existing function

class Command(BaseCommand):
    help = "Extract, chunk, embed, and index ALL papers in the database."

    def handle(self, *args, **kwargs):
        papers = Paper.objects.all()
        if not papers.exists():
            self.stdout.write(self.style.WARNING("No papers found in DB."))
            return

        for i, paper in enumerate(papers, start=1):
            self.stdout.write(f"[{i}/{len(papers)}] Indexing: {paper.title}")

            # Delete old chunks for this paper
            PaperChunk.objects.filter(paper=paper).delete()

            try:
                index_paper(paper)
                self.stdout.write(self.style.SUCCESS(f"✓ Indexed {paper.title}"))
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ Failed {paper.title}: {e}")
                )

        self.stdout.write(self.style.SUCCESS("All papers indexed successfully."))
