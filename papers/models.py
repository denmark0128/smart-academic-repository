from django.db import models


class Paper(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=100)
    abstract = models.TextField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='papers/')

    def __str__(self):
        return self.title