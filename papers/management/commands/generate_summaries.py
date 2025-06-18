from django.core.management.base import BaseCommand
from papers.models import Paper
from papers.utils.nlp import extract_tags

class Command(BaseCommand):
    help = 'Extract and update tags for all existing papers.'

    def handle(self, *args, **options):
        papers = Paper.objects.all()
        count = 0
        for paper in papers:
            if paper.abstract:
                tags = extract_tags(paper.abstract)
                paper.tags = tags
                paper.save()
                self.stdout.write(f'Updated tags for: {paper.title} ({len(tags)} tags)')
                count += 1
        self.stdout.write(self.style.SUCCESS(f'Updated tags for {count} papers.'))
