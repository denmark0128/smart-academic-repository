from django.core.management.base import BaseCommand
from papers.models import Paper
from utils.semantic_search import build_full_index
import os

class Command(BaseCommand):
    help = 'Build FAISS index from all uploaded PDFs.'

    def handle(self, *args, **options):
        papers = Paper.objects.all()
        if not papers:
            self.stdout.write(self.style.WARNING('No papers found.'))
            return
        paper_list = []
        for paper in papers:
            pdf_path = paper.file.path
            title = paper.title
            author = paper.author
            paper_list.append({'pdf_path': pdf_path, 'title': title, 'author': author})
        self.stdout.write(f'Indexing {len(paper_list)} papers...')
        build_full_index(paper_list)
        self.stdout.write(self.style.SUCCESS('FAISS index built successfully.'))
