from django.core.management.base import BaseCommand
from papers.models import Paper
from utils.semantic_search import get_model

class Command(BaseCommand):
    help = "Embed title and abstract for all papers without embeddings"

    def handle(self, *args, **options):
        model = get_model()
        updated = 0

        for paper in Paper.objects.all():
            changed_fields = []

            if paper.title and not paper.title_embedding:
                try:
                    paper.title_embedding = model.encode(paper.title).tolist()
                    changed_fields.append("title_embedding")
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"Error embedding title for {paper.id}: {e}"
                    ))

            if paper.abstract and not paper.abstract_embedding:
                try:
                    paper.abstract_embedding = model.encode(paper.abstract).tolist()
                    changed_fields.append("abstract_embedding")
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"Error embedding abstract for {paper.id}: {e}"
                    ))

            if changed_fields:
                paper.save(update_fields=changed_fields)
                updated += 1
                self.stdout.write(self.style.SUCCESS(
                    f"Updated Paper {paper.id} ({', '.join(changed_fields)})"
                ))

        self.stdout.write(self.style.SUCCESS(f"✅ Done. Updated {updated} papers."))
