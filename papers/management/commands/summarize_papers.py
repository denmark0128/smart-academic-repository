import os
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from papers.models import Paper
from utils.summarize import summarize_pdf_to_json


class Command(BaseCommand):
    help = "Re-summarize ALL papers: deletes existing summaries and regenerates them using the local llama.cpp model."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("⚠️  Deleting all existing summaries..."))
        updated = Paper.objects.update(summary=None)
        self.stdout.write(self.style.SUCCESS(f"🗑 Cleared summaries for {updated} papers."))

        papers = Paper.objects.all()
        if not papers.exists():
            self.stdout.write(self.style.WARNING("No papers found to summarize."))
            return

        self.stdout.write(self.style.SUCCESS(f"🧠 Found {papers.count()} paper(s) to summarize."))

        for paper in papers:
            try:
                pdf_path = paper.file.path
                self.stdout.write(f"\n📄 Summarizing: {paper.title}")

                # Summarize and get structured data
                data = summarize_pdf_to_json(pdf_path)

                if not isinstance(data, dict) or "summary" not in data:
                    raise ValueError("summarize_pdf_to_json() must return a dict containing 'summary'.")

                # ✅ Reconnect before saving
                close_old_connections()

                paper.summary = data["summary"]
                paper.save(update_fields=["summary"])

                self.stdout.write(self.style.SUCCESS(f"✅ Done: {paper.title}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error summarizing {paper.title}: {e}"))
