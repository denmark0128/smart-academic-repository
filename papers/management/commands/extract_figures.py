from django.core.management.base import BaseCommand
from django.core.files import File
from papers.models import Paper, ExtractedFigure
from utils.figure_extract import extract_images_from_pdf
from django.conf import settings
import os

class Command(BaseCommand):
    help = "Extracts figures from all uploaded papers' PDFs"

    def handle(self, *args, **options):
        papers = Paper.objects.all()
        media_root = getattr(settings, "MEDIA_ROOT", "media")
        extracted_root = os.path.join(media_root, "extracted")
        os.makedirs(extracted_root, exist_ok=True)

        for paper in papers:
            if not paper.file:  # adjust field name if needed
                self.stdout.write(self.style.WARNING(f"Skipping {paper.id}: no PDF"))
                continue

            pdf_path = paper.file.path
            paper_folder = os.path.join(extracted_root, f"paper_{paper.id}")
            os.makedirs(paper_folder, exist_ok=True)

            self.stdout.write(f"Processing {pdf_path} ...")
            try:
                saved_files = extract_images_from_pdf(pdf_path, paper_folder)

                for image_path in saved_files:
                    page_num = int(image_path.split("_img")[0].split("page")[-1])  # crude but works
                    with open(image_path, "rb") as f:
                        ExtractedFigure.objects.create(
                            paper=paper,
                            image=File(f, name=os.path.basename(image_path)),
                            page_number=page_num,
                        )

                self.stdout.write(self.style.SUCCESS(
                    f"Saved {len(saved_files)} ExtractedFigure records for paper {paper.id}"
                ))

            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"Error extracting from paper {paper.id}: {e}"
                ))
