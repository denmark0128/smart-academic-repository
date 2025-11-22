# staff/forms.py
from django import forms
from .models import SearchSettings, LlamaSettings

class SearchSettingsForm(forms.ModelForm):
    class Meta:
        model = SearchSettings
        fields = [
            'embedding_model_name',
            'chunk_size', 
            'chunk_overlap', 
            'appendix_cutoff',
            'top_k_results', 
            'min_similarity_score',
            'bm25_weight', 
            'vector_weight',
            'max_chunks_scan', 
            'hybrid_search_multiplier',
            'hybrid_search_min_results',
            'tag_extraction_top_n',
            'tag_extraction_min_score',
            'tag_cache_timeout',
            'settings_cache_timeout', # <-- Make sure this field exists in the form
        ]
        widgets = {
            'embedding_model_name': forms.TextInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'chunk_size': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'chunk_overlap': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'appendix_cutoff': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'top_k_results': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'min_similarity_score': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2', 'step': '0.01'}),
            'bm25_weight': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2', 'step': '0.1'}),
            'vector_weight': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2', 'step': '0.1'}),
            'max_chunks_scan': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'hybrid_search_multiplier': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'hybrid_search_min_results': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'tag_extraction_top_n': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'tag_extraction_min_score': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2', 'step': '0.01'}),
            'tag_cache_timeout': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'settings_cache_timeout': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
        }

class LlamaSettingsForm(forms.ModelForm):
    class Meta:
        model = LlamaSettings
        fields = [
            'repo_id',
            'model_filename',
            'model_seed',
            'n_ctx',
            'system_prompt',
            'user_prompt_template',
            'generation_seed',
            'temperature',
            'max_tokens',
            'top_p',
            'settings_cache_timeout',
        ]
        widgets = {
            # --- Model Loading ---
            'repo_id': forms.TextInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'model_filename': forms.TextInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'model_seed': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'n_ctx': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),

            # --- Prompts ---
            'system_prompt': forms.Textarea(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2', 'rows': 4}),
            'user_prompt_template': forms.Textarea(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2', 'rows': 4}),

            # --- Generation Params ---
            'generation_seed': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'temperature': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2', 'step': '0.1'}),
            'max_tokens': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
            'top_p': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2', 'step': '0.01'}),
            
            # --- Caching ---
            'settings_cache_timeout': forms.NumberInput(attrs={'class': 'w-full border border-gray-200 dark:border-zinc-700 rounded-lg p-2'}),
        }
    