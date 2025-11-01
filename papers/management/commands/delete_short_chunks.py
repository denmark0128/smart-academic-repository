from django.core.management.base import BaseCommand
from papers.models import PaperChunk  # adjust to your model path

class Command(BaseCommand):
    help = "Deletes all PaperChunk entries with text shorter than 5 words."

    def handle(self, *args, **options):
        total = PaperChunk.objects.count()

        # Filter chunks with <5 words
        short_chunks = PaperChunk.objects.filter()
        short_chunks = [chunk for chunk in short_chunks if len(chunk.text.split()) < 5]

        count = len(short_chunks)
        ids = [chunk.id for chunk in short_chunks]

        if count == 0:
            self.stdout.write(self.style.SUCCESS("✅ No short chunks found."))
            return

        # Delete them
        PaperChunk.objects.filter(id__in=ids).delete()

        self.stdout.write(
            self.style.WARNING(f"🧹 Deleted {count} chunks out of {total} that had fewer than 5 words.")
        )
from django.core.management.base import BaseCommand
from papers.models import PaperChunk  # adjust to your model path

class Command(BaseCommand):
    help = "Deletes all PaperChunk entries with text shorter than 5 words."

    def handle(self, *args, **options):
        total = PaperChunk.objects.count()

        # Filter chunks with <5 words
        short_chunks = PaperChunk.objects.filter()
        short_chunks = [chunk for chunk in short_chunks if len(chunk.text.split()) < 5]

        count = len(short_chunks)
        ids = [chunk.id for chunk in short_chunks]

        if count == 0:
            self.stdout.write(self.style.SUCCESS("✅ No short chunks found."))
            return

        # Delete them
        PaperChunk.objects.filter(id__in=ids).delete()

        self.stdout.write(
            self.style.WARNING(f"🧹 Deleted {count} chunks out of {total} that had fewer than 5 words.")
        )
