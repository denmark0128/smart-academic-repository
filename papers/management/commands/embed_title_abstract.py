import numpy as np
from django.core.management.base import BaseCommand
from django.db.models import Q
from papers.models import Paper
from papers.utils.nlp import get_embedding_model

class Command(BaseCommand):
    help = 'Generates title and abstract embeddings for existing papers.'

    def add_arguments(self, parser):
        """
        Add an optional --force argument.
        """
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force regeneration of embeddings even if they already exist.',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('Loading embedding model...'))
        try:
            model = get_embedding_model() # Load model once
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Failed to load embedding model: {e}"))
            return
            
        self.stdout.write(self.style.SUCCESS('Embedding model loaded.'))

        force_run = options['force']
        
        if force_run:
            self.stdout.write(self.style.WARNING('FORCING regeneration for ALL papers...'))
            papers_to_process = Paper.objects.all()
        else:
            self.stdout.write(self.style.NOTICE('Processing papers with MISSING embeddings...'))
            # Get all papers where either embedding is null
            papers_to_process = Paper.objects.filter(
                Q(title_embedding__isnull=True) | Q(abstract_embedding__isnull=True)
            )

        count = papers_to_process.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No papers to process. All embeddings are up to date!'))
            return

        self.stdout.write(f'Found {count} papers to process.')
        updated_papers_count = 0
        processed_count = 0

        for paper in papers_to_process.iterator(): # Use .iterator() for memory efficiency
            processed_count += 1
            fields_to_update = []
            
            # --- Process Title ---
            # Check if we should process this field
            if (force_run or paper.title_embedding is None) and paper.title:
                try:
                    paper.title_embedding = model.encode(paper.title, convert_to_numpy=True)
                    fields_to_update.append('title_embedding')
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'  > FAILED title embedding for Paper ID {paper.id}: {e}'))
            
            # --- Process Abstract ---
            # Check if we should process this field
            if (force_run or paper.abstract_embedding is None) and paper.abstract:
                try:
                    paper.abstract_embedding = model.encode(paper.abstract, convert_to_numpy=True)
                    fields_to_update.append('abstract_embedding')
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'  > FAILED abstract embedding for Paper ID {paper.id}: {e}'))
            
            # --- Save if needed ---
            if fields_to_update:
                paper.save(update_fields=fields_to_update)
                updated_papers_count += 1
            
            if processed_count % 100 == 0:
                self.stdout.write(f'  ...processed {processed_count} / {count} papers...')

        self.stdout.write(self.style.SUCCESS(f'\nProcessing complete. Successfully updated {updated_papers_count} papers.'))