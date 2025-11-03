from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

# Create your models here.
# papers/models.py (add to your existing models)

class SearchSettings(models.Model):
    """Configurable settings for paper search and indexing"""
    
    embedding_model_name = models.CharField(
        max_length=255, 
        default="ibm-granite/granite-embedding-english-r2",
        help_text="The HuggingFace repo ID or local path for the embedding model."
    )

    # Chunking settings
    chunk_size = models.IntegerField(
        default=1000,
        validators=[MinValueValidator(100), MaxValueValidator(5000)],
        help_text="Size of text chunks for embedding"
    )
    chunk_overlap = models.IntegerField(
        default=200,
        validators=[MinValueValidator(0), MaxValueValidator(1000)],
        help_text="Overlap between consecutive chunks"
    )
    appendix_cutoff = models.IntegerField(
        default=5000,
        help_text="Character count after which to check for appendices"
    )
    
    # Search settings
    top_k_results = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
        help_text="Number of top results to return"
    )
    min_similarity_score = models.FloatField(
        default=0.25,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Minimum similarity score threshold"
    )
    bm25_weight = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Weight for BM25 keyword matching"
    )
    vector_weight = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Weight for vector similarity"
    )
    
    # Keyword search settings
    max_chunks_scan = models.IntegerField(
        default=2000,
        validators=[MinValueValidator(100), MaxValueValidator(10000)],
        help_text="Maximum chunks to scan in keyword search"
    )
    hybrid_search_multiplier = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Multiplier for initial hybrid search (top_k * multiplier)"
    )
    hybrid_search_min_results = models.IntegerField(
        default=20,
        help_text="Minimum results to fetch for hybrid search"
    )
    tag_extraction_top_n = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(20)],
        help_text="Number of top tags to extract"
    )
    tag_extraction_min_score = models.FloatField(
        default=0.5,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Minimum similarity score for tag extraction"
    )
    tag_cache_timeout = models.IntegerField(
        default=3600,
        validators=[MinValueValidator(300), MaxValueValidator(86400)],
        help_text="Cache timeout for tags in seconds (default: 1 hour)"
    )
    settings_cache_timeout = models.IntegerField(
        default=900, 
        help_text="How long to cache these settings (seconds). 15 min = 900."
    )
    class Meta:
        verbose_name_plural = "Search Settings"
    
    def save(self, *args, **kwargs):
        from django.core.cache import cache
        self.pk = 1  
        cache.delete('active_search_settings') 
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
    
class LlamaSettings(models.Model):
    """
    Singleton model to store Llama settings dynamically in the database.
    """
    # Model Loading
    repo_id = models.CharField(max_length=255, default="unsloth/gemma-3-1b-it-GGUF")
    model_filename = models.CharField(max_length=255, default="gemma-3-1b-it-BF16.gguf")
    model_seed = models.IntegerField(default=4)
    n_ctx = models.IntegerField(default=32000, help_text="Context window size")

    # Generation
    system_prompt = models.TextField(
        default="You are an academic summarizer that writes clear and concise summaries."
    )
    user_prompt_template = models.TextField(
        default="Summarize this paper concisely and detailed:\n\n{text}"
    )
    generation_seed = models.IntegerField(default=2)
    
    # Optional Generation Params
    temperature = models.FloatField(
        null=True, blank=True, default=0.7, 
        help_text="Controls randomness. Lower is more deterministic. (e.g., 0.7)"
    )
    max_tokens = models.IntegerField(
        null=True, blank=True, 
        help_text="Max tokens to generate. Null means no limit."
    )
    top_p = models.FloatField(
        null=True, blank=True, default=0.95, 
        help_text="Nucleus sampling. (e.g., 0.95)"
    )
    
    # Caching
    settings_cache_timeout = models.IntegerField(
        default=900, help_text="How long to cache these settings (seconds). 15 min = 900."
    )
    
    class Meta:
        verbose_name_plural = "Llama Settings"

    def __str__(self):
        return f"Llama Settings ({self.repo_id})"

    def save(self, *args, **kwargs):
        self.pk = 1
        from django.core.cache import cache
        cache.delete('active_llama_settings')
        super().save(*args, **kwargs)
    
    @classmethod
    def get_settings(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
