import os
from django.core.management.base import BaseCommand
from django.conf import settings
from papers.models import Paper

class Command(BaseCommand):
    help = 'Deletes orphaned PDF files in the media/papers/ folder'

    def handle(self, *args, **kwargs):
        papers_dir = os.path.join(settings.MEDIA_ROOT, 'papers')
        used_files = set(paper.file.name for paper in Paper.objects.all())

        deleted = 0
        for filename in os.listdir(papers_dir):
            file_path = os.path.join('papers', filename)
            full_path = os.path.join(settings.MEDIA_ROOT, file_path)
            if file_path not in used_files:
                os.remove(full_path)
                self.stdout.write(f"Deleted unused file: {file_path}")
                deleted += 1

        self.stdout.write(self.style.SUCCESS(f"Cleanup complete. Deleted {deleted} unused PDF(s)."))
