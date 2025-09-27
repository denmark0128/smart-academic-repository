import pprint
from django.core.management.base import BaseCommand
from papers.models import Paper, PaperChunk
from utils.semantic_search import get_model  # your SentenceTransformer wrapper

class Command(BaseCommand):
    help = 'Rebuild embeddings for all uploaded papers and store them in DB (pgvector).'

    def handle(self, *args, **options):
        model = get_model()

        # Delete all old chunks globally
        PaperChunk.objects.all().delete()
        self.stdout.write(self.style.WARNING("Deleted all old chunks."))

        papers = Paper.objects.all()
        if not papers:
            self.stdout.write(self.style.WARNING('No papers found.'))
            return

        for i, paper in enumerate(papers, 1):
            self.stdout.write(f"[{i}/{len(papers)}] Processing {paper.title}")

            # Load + chunk text (replace with your smart chunking function)
            text = paper.abstract or ""
            chunks = [text]  # Example: one chunk per abstract

            # Encode chunks
            embeddings = model.encode(chunks, convert_to_numpy=True)

            # Create chunks with sequential chunk_id
            for idx, (chunk_text, emb) in enumerate(zip(chunks, embeddings)):
                PaperChunk.objects.create(
                    paper=paper,
                    chunk_id=idx,  # sequential ID per paper
                    text=chunk_text,
                    embedding=emb.tolist()
                )

        self.stdout.write(self.style.SUCCESS('Index rebuilt successfully.'))
