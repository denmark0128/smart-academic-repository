from django.contrib import admin
from .models import SearchSettings, LlamaSettings

# Register your models here.
admin.site.register(SearchSettings)
admin.site.register(LlamaSettings)
