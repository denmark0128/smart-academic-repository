from django.db import models
from django.contrib.auth.models import User

class Paper(models.Model):
    title = models.CharField(max_length=200)
    authors = models.JSONField(default=list) 
    abstract = models.TextField(blank=True, null=True)
    college = models.CharField(max_length=100, blank=True, null=True)
    program = models.CharField(max_length=100, blank=True, null=True)
    summary = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='papers/')
    tags = models.JSONField(default=list, blank=True)
    is_indexed = models.BooleanField(default=False)

    year = models.PositiveIntegerField(null=True, blank=True) 

    def __str__(self):
        return self.title
    
    def citations_pointing_here(self):
        return MatchedCitation.objects.filter(matched_paper=self)
    
    def citation_count(self):
        return MatchedCitation.objects.filter(matched_paper=self).count()


class SavedPaper(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_papers')
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE)
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'paper')

class MatchedCitation(models.Model):
    source_paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name="matched_citations")
    matched_paper = models.ForeignKey(Paper, on_delete=models.SET_NULL, null=True, blank=True)
    raw_citation = models.TextField()
    score = models.FloatField()
    matched_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.source_paper.title} → {self.matched_paper.title if self.matched_paper else 'Unknown'}"
