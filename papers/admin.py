from django.contrib import admin
from .models import Paper, SavedPaper
# Register your models here.
admin.site.register(Paper)
admin.site.register(SavedPaper)