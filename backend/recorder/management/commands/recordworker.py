from django.core.management.base import BaseCommand
from recorder.worker import runWorker


class Command(BaseCommand):
    help = 'Ejecuta la comprobación periódica y grabaciones paralelas (única réplica)'

    def handle(self, *args, **options):
        runWorker()
