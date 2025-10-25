from django.core.management.base import BaseCommand
from django.db import transaction
from papers.models import Paper
from utils.tagging import extract_tags_from_paper, extract_tags_with_chunks

class Command(BaseCommand):
    help = 'Extract and update tags for all existing papers.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--use-chunks',
            action='store_true',
            help='Use paper chunks for better context (slower but more accurate)',
        )
        parser.add_argument(
            '--chunk-limit',
            type=int,
            default=10,
            help='Number of chunks to use for context (default: 10)',
        )
        parser.add_argument(
            '--top-n',
            type=int,
            default=5,
            help='Number of tags to extract per paper (default: 5)',
        )
        parser.add_argument(
            '--min-score',
            type=float,
            default=0.50,
            help='Minimum semantic similarity score (default: 0.50)',
        )
        parser.add_argument(
            '--no-keyword-check',
            action='store_true',
            help='Allow tags even if keywords don\'t appear in text',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of papers to process before committing (default: 100)',
        )

    def handle(self, *args, **options):
        use_chunks = options['use_chunks']
        chunk_limit = options['chunk_limit']
        top_n = options['top_n']
        min_score = options['min_score']
        require_keyword_presence = not options['no_keyword_check']
        batch_size = options['batch_size']

        papers = Paper.objects.all()
        total_count = papers.count()
        updated_count = 0
        error_count = 0
        skipped_count = 0

        self.stdout.write(self.style.NOTICE(
            f"Found {total_count} papers. Starting tag extraction...\n"
            f"Mode: {'With chunks' if use_chunks else 'Title + Abstract only'}\n"
            f"Settings: top_n={top_n}, min_score={min_score}, "
            f"require_keyword_presence={require_keyword_presence}\n"
        ))

        # Process in batches
        for batch_start in range(0, total_count, batch_size):
            batch_papers = papers[batch_start:batch_start + batch_size]
            
            with transaction.atomic():
                for paper in batch_papers:
                    try:
                        # Check if paper has required content
                        if not paper.title and not paper.abstract:
                            skipped_count += 1
                            self.stdout.write(
                                self.style.WARNING(f"⊘ Skipping paper ID {paper.id} (no title or abstract)")
                            )
                            continue

                        # Extract tags based on mode
                        if use_chunks:
                            tags = extract_tags_with_chunks(
                                paper_model=paper,
                                chunk_limit=chunk_limit,
                                top_n=top_n,
                                min_semantic_score=min_score
                            )
                        else:
                            tags = extract_tags_from_paper(
                                title=paper.title,
                                abstract=paper.abstract,
                                top_n=top_n,
                                min_semantic_score=min_score,
                                require_keyword_presence=require_keyword_presence
                            )

                        # Update paper
                        paper.tags = tags
                        paper.save(update_fields=["tags"])

                        updated_count += 1
                        
                        # Show progress
                        tag_display = ", ".join(tags[:3]) + ("..." if len(tags) > 3 else "")
                        self.stdout.write(
                            f"✅ [{updated_count}/{total_count}] {paper.title[:50]}... "
                            f"({len(tags)} tags: {tag_display})"
                        )

                    except Exception as e:
                        error_count += 1
                        self.stderr.write(
                            self.style.ERROR(
                                f"❌ Error processing '{paper.title[:50]}...': {e}"
                            )
                        )

            # Progress update after each batch
            self.stdout.write(
                self.style.NOTICE(
                    f"\nBatch completed. Progress: {updated_count + error_count + skipped_count}/{total_count}\n"
                )
            )

        # Final summary
        self.stdout.write("\n" + "="*60)
        self.stdout.write(self.style.SUCCESS(
            f"✓ Tag extraction completed!\n"
            f"  • Successfully updated: {updated_count} papers\n"
            f"  • Skipped (no content): {skipped_count} papers\n"
            f"  • Errors: {error_count} papers\n"
            f"  • Total processed: {total_count} papers"
        ))