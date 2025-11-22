from django.core.management.base import BaseCommand
from papers.models import Paper

class Command(BaseCommand):
    help = "Assign or replace local DOIs for all papers."

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Replace existing DOIs for all papers.'
        )

    def handle(self, *args, **options):
        replace = options['replace']
        updated = 0

        for paper in Paper.objects.all():
            if replace or not paper.local_doi:
                paper.local_doi = f"plp/{paper.college}.{paper.year}.{paper.program}.{str(paper.pk).zfill(5)}"
                paper.save()
                updated += 1
                self.stdout.write(self.style.SUCCESS(
                    f"{'Reassigned' if replace else 'Assigned'} DOI to paper ID {paper.pk}: {paper.local_doi}"
                ))

        if updated == 0:
            self.stdout.write(self.style.WARNING("No papers needed DOI assignment."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{'Reassigned' if replace else 'Assigned'} DOIs to {updated} paper(s)."))
