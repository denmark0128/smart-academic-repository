from django.contrib import admin
from .models import Paper, SavedPaper, MatchedCitation
# Register your models here.
admin.site.register(Paper)
admin.site.register(SavedPaper)
admin.site.site_header = "Paper Repository Admin"
admin.site.register(MatchedCitation)