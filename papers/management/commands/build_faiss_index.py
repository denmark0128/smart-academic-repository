import os
import pprint
from django.core.management.base import BaseCommand
from papers.models import Paper
from utils.semantic_search import build_full_index

FAISS_INDEX_PATH = "media/indices/paragraphs.index"      # Path to FAISS index
FAISS_METADATA_PATH = "media/indices/paragraphs_metadata.json"  # Path to metadata JSON

class Command(BaseCommand):
    help = 'Rebuild FAISS index from all uploaded PDFs, deleting old index and metadata first.'

    def handle(self, *args, **options):
        # Delete old FAISS index
        if os.path.exists(FAISS_INDEX_PATH):
            os.remove(FAISS_INDEX_PATH)
            self.stdout.write(self.style.WARNING(f"Deleted old FAISS index at {FAISS_INDEX_PATH}"))

        # Delete old metadata
        if os.path.exists(FAISS_METADATA_PATH):
            os.remove(FAISS_METADATA_PATH)
            self.stdout.write(self.style.WARNING(f"Deleted old FAISS metadata at {FAISS_METADATA_PATH}"))

        papers = Paper.objects.all()
        if not papers:
            self.stdout.write(self.style.WARNING('No papers found.'))
            return

        paper_list = []
        for paper in papers:
            pdf_path = paper.file.path
            title = paper.title
            authors = paper.authors if isinstance(paper.authors, list) else [paper.authors]
            paper_list.append({
                'pdf_path': pdf_path,
                'title': title,
                'authors': authors
            })

        self.stdout.write(f'Indexing {len(paper_list)} papers...')
        pprint.pprint(paper_list)

        build_full_index(paper_list)
        self.stdout.write(self.style.SUCCESS('FAISS index built successfully.'))
