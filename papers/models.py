from django.db import models
from django.contrib.auth.models import User
from pgvector.django import VectorField

COLLEGE_CHOICES = [
    ('ccs', 'College of Computer Studies'),
    ('cba', 'College of Business and Accountancy'),
    ('cas', 'College of Arts and Sciences'),
    ('coe', 'College of Engineering'),
    ('cihm','College of International Hospitality Management'),
    # add more as needed
]

PROGRAM_CHOICES = [
    ('bsit', 'BS in Information Technology'),
    ('bscs', 'BS in Computer Science'),
    ('bsba', 'BS in Business Administration'),
    ('bse', 'BS in Secondary Education'),
    ('bsa', 'BS in Accountancy'),
    # add more as needed
]

class Paper(models.Model):
    local_doi = models.CharField(max_length=100, unique=True, null=True, blank=True)
    title = models.CharField(max_length=200)
    title_embedding = VectorField(dimensions=384, null=True)
    authors = models.JSONField(default=list) 
    abstract = models.TextField(blank=True, null=True)
    abstract_embedding = VectorField(dimensions=384, null=True)
    college = models.CharField(max_length=100, blank=True, null=True, choices=COLLEGE_CHOICES)
    program = models.CharField(max_length=100, blank=True, null=True, choices=PROGRAM_CHOICES)
    summary = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='papers/')
    tags = models.JSONField(default=list, blank=True)
    is_indexed = models.BooleanField(default=False)
    is_registered = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="pending")
    year = models.PositiveIntegerField(null=True, blank=True) 

    """
    STATUS_CHOICES = [
        ("uploaded", "Uploaded"),
        ("processing", "Processing"),
        ("ready", "Ready for Review"),
        ("complete", "Complete"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="uploaded")
    """
    def __str__(self):
        return self.title
    
    def citations_pointing_here(self):
        return MatchedCitation.objects.filter(matched_paper=self)
    
    def citation_count(self):
        return MatchedCitation.objects.filter(matched_paper=self).count()
    
class PaperChunk(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE,null=True, related_name="chunks")
    title = models.TextField(null=True, blank=True)
    authors = models.JSONField(null=True, blank=True)  # store list of authors
    page = models.IntegerField(null=True, blank=True)
    chunk_id = models.IntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=384)  # MiniLM-L6-v2 = 384 dims

    class Meta:
        indexes = [
            models.Index(fields=["paper_id"]),
        ]


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

