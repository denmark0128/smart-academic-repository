# papers/migrations/0XXX_add_search_indexes.py
from django.db import migrations

class Migration(migrations.Migration):
    dependencies = [
        ('papers', '0025_paper_images_folder_paper_merged_html'),
    ]

    operations = [
        # Enable required extensions
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector CASCADE;"
        ),
        migrations.RunSQL(
            "CREATE EXTENSION IF NOT EXISTS btree_gin;",
            reverse_sql="DROP EXTENSION IF EXISTS btree_gin CASCADE;"
        ),
        
        # ✅ GIN index for full-text search (BM25)
        migrations.RunSQL(
            """
            CREATE INDEX IF NOT EXISTS paperchunk_text_gin_idx 
            ON papers_paperchunk 
            USING GIN (to_tsvector('english', text));
            """,
            reverse_sql="DROP INDEX IF EXISTS paperchunk_text_gin_idx;"
        ),
        
        # ✅ HNSW index for vector similarity search
        migrations.RunSQL(
            """
            CREATE INDEX IF NOT EXISTS paperchunk_embedding_hnsw_idx 
            ON papers_paperchunk 
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
            """,
            reverse_sql="DROP INDEX IF EXISTS paperchunk_embedding_hnsw_idx;"
        ),
    ]