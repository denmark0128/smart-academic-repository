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

        with transaction.atomic():
            for paper in papers:
                try:
                    text = " ".join([paper.title or "", paper.abstract or ""]).strip()
                    if not text:
                        self.stdout.write(self.style.WARNING(f"Skipping '{paper.title}' (no content)"))
                        continue

                    # extract_tags returns list of dicts with name, description, score
                    tags_data = extract_tags(text)

                    # Store only the tag names in the JSONField
                    tag_names = [tag['name'] for tag in tags_data]
                    paper.tags = tag_names
                    paper.save(update_fields=['tags'])

                    updated_count += 1
                    self.stdout.write(f"✅ Updated: {paper.title} ({len(tag_names)} tags)")

                except Exception as e:
                    error_count += 1
                    self.stderr.write(f"❌ Error processing '{paper.title}': {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Completed tag updates: {updated_count} papers updated, {error_count} errors."
        ))
