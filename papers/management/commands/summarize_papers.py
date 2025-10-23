import os
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from papers.models import Paper, PaperChunk
from utils.summarize import summarize_full_text  # note: no summarize_pdf_to_json

class Command(BaseCommand):
    help = "Re-summarize paper(s) by joining their chunks and summarizing them with the local llama.cpp model."

    def add_arguments(self, parser):
        parser.add_argument(
            "--title",
            type=str,
            help="Title of the paper to summarize (optional). If omitted, summarizes all papers.",
        )

    def handle(self, *args, **options):
        title = options.get("title")

        # --- Filter papers ---
        if title:
            papers = Paper.objects.filter(title=title)
            if not papers.exists():
                self.stdout.write(self.style.ERROR(f"❌ No paper found with title '{title}'"))
                return
            self.stdout.write(self.style.SUCCESS(f"🧠 Summarizing paper titled: {title}"))
        else:
            self.stdout.write(self.style.WARNING("⚠️  Deleting all existing summaries..."))
            updated = Paper.objects.update(summary=None)
            self.stdout.write(self.style.SUCCESS(f"🗑 Cleared summaries for {updated} papers."))
            papers = Paper.objects.all()

        # --- Process each paper ---
        for paper in papers:
            try:
                self.stdout.write(f"\n📄 Summarizing from chunks: {paper.title}")

                # Gather all chunks for this paper
                chunks = PaperChunk.objects.filter(paper=paper).order_by("chunk_id")
                if not chunks.exists():
                    self.stdout.write(self.style.WARNING(f"⚠️ No chunks found for {paper.title}, skipping."))
                    continue

                full_text = " ".join(chunk.text for chunk in chunks)
                print(f"📝 Full text length: {len(full_text)} characters")
                # Summarize using local llama.cpp model
                summary = summarize_full_text(full_text, title=paper.title)

                # Reconnect before saving (important for long loops)
                close_old_connections()

                paper.summary = summary
                paper.save(update_fields=["summary"])

                self.stdout.write(self.style.SUCCESS(f"✅ Done: {paper.title}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error summarizing {paper.title}: {e}"))
