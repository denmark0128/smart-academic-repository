# staff/utils.py
from django.core.cache import cache
from .models import SearchSettings, LlamaSettings

def get_search_settings():
    """
    Get the active SearchSettings instance.
    Uses an in-memory (lru_cache) and a shared (cache) cache.
    """
    cache_key = 'active_search_settings' # <-- Standardized key
    settings_obj = cache.get(cache_key)
    
    if settings_obj is None:
        print("[StaffUtils] Search settings cache miss. Fetching from DB.")
        
        # Use the standard class method
        settings_obj = SearchSettings.get_settings() 
        
        # Use the timeout *from the settings object*
        cache.set(cache_key, settings_obj, settings_obj.settings_cache_timeout)
    else:
        print("[StaffUtils] Search settings cache hit.")
        
    return settings_obj


def get_llama_settings():
    """
    Get the active LlamaSettings instance.
    Uses an in-memory (lru_cache) and a shared (cache) cache.
    """
    cache_key = 'active_llama_settings'
    settings_obj = cache.get(cache_key)
    
    if settings_obj is None:
        print("[StaffUtils] Llama settings cache miss. Fetching from DB.")
        
        # Use the standard class method
        settings_obj = LlamaSettings.get_settings() 
        
        # Use the timeout *from the settings object*
        cache.set(cache_key, settings_obj, settings_obj.settings_cache_timeout)
    else:
        print("[StaffUtils] Llama settings cache hit.")
        
    return settings_obj