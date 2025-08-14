from django.core.management.base import BaseCommand
from django.db import transaction
from papers.models import Paper
from papers.utils.nlp import extract_tags

class Command(BaseCommand):
    help = 'Extract and update tags for all existing papers.'

    def handle(self, *args, **options):
        papers = Paper.objects.all()
        updated_count = 0
        error_count = 0

        self.stdout.write(self.style.NOTICE(f"Found {papers.count()} papers. Starting tag update..."))

        # Use a transaction so all updates are atomic
        with transaction.atomic():
            for paper in papers:
                try:
                    combined_text = " ".join([
                        paper.title or "",
                        paper.abstract or "",
                        paper.summary or ""
                    ]).strip()

                    if not combined_text:
                        self.stdout.write(self.style.WARNING(f"Skipping '{paper.title}' (no content)"))
                        continue

                    tags = extract_tags(combined_text)
                    paper.tags = tags
                    paper.save(update_fields=["tags"])

                    updated_count += 1
                    self.stdout.write(f"✅ Updated: {paper.title} ({len(tags)} tags)")

                except Exception as e:
                    error_count += 1
                    self.stderr.write(f"❌ Error processing '{paper.title}': {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Completed tag updates: {updated_count} papers updated, {error_count} errors."
        ))
