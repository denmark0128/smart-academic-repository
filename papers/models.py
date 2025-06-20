from django.db import models
from django.contrib.auth.models import User


class Paper(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=100)
    abstract = models.TextField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='papers/')
    tags = models.JSONField(default=list, blank=True)  # Store tags as a list of strings

    def __str__(self):
        return self.title
    
class SavedPaper(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_papers')
    paper = models.ForeignKey('Paper', on_delete=models.CASCADE)
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'paper')  # Prevent duplicate saves