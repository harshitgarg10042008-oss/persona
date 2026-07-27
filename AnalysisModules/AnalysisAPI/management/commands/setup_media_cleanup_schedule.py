from django.core.management.base import BaseCommand
from django_q.models import Schedule


class Command(BaseCommand):
    help = 'Set up daily schedule for media retention cleanup task'

    def handle(self, *args, **options):
        # Check if schedule already exists
        existing = Schedule.objects.filter(
            func='AnalysisAPI.tasks.cleanup_old_media_task'
        ).first()
        
        if existing:
            self.stdout.write(
                self.style.WARNING(
                    'Media cleanup schedule already exists. '
                    'Deleting old schedule and creating new one.'
                )
            )
            existing.delete()
        
        # Create daily schedule
        schedule = Schedule.objects.create(
            func='AnalysisAPI.tasks.cleanup_old_media_task',
            name='Daily Media Retention Cleanup',
            schedule_type=Schedule.DAILY,
            repeats=-1,  # Repeat indefinitely
            next_run=None,  # Let Django-Q calculate next run time
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created daily media cleanup schedule (ID: {schedule.id})'
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                'The cleanup task will run daily at the time configured in Django-Q cluster settings.'
            )
        )
