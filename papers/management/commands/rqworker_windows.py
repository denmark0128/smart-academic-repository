# papers/management/commands/rqworker_windows.py
from django.core.management.base import BaseCommand
from django_rq import get_worker

class Command(BaseCommand):
    help = 'Run RQ worker compatible with Windows'

    def add_arguments(self, parser):
        parser.add_argument('queues', nargs='*', default=['default'], type=str)

    def handle(self, *args, **options):
        queues = options['queues']
        self.stdout.write(f'Starting worker for queues: {queues}')
        
        worker = get_worker(*queues)
        worker.work(with_scheduler=True, burst=False)