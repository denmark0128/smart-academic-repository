from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import MatchedCitation, Paper

@receiver([post_save, post_delete], sender=MatchedCitation)
def update_citation_cache(sender, instance, **kwargs):
    source = instance.source_paper
    matched = instance.matched_paper

    if source:
        source.matched_count_cached = source.matched_citations.count()
        source.save(update_fields=["matched_count_cached"])

    if matched:
        matched.citation_count_cached = matched.reverse_matched_citations.count()
        matched.save(update_fields=["citation_count_cached"])
