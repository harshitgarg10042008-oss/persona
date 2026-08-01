"""
Management command to activate Premium for any user account.

Usage:
    python manage.py activate_premium --email user@example.com
    python manage.py activate_premium --email user@example.com --days 30
    python manage.py activate_premium --email user@example.com --lifetime
    python manage.py activate_premium --list-free     (list all free users)
    python manage.py activate_premium --email user@example.com --deactivate  (revert to free)
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Activate or deactivate Premium for a user account"

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='Email of the user to activate/deactivate premium for',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Number of days for premium (default: lifetime)',
        )
        parser.add_argument(
            '--lifetime',
            action='store_true',
            help='Activate lifetime premium (no expiry)',
        )
        parser.add_argument(
            '--deactivate',
            action='store_true',
            help='Deactivate premium and revert user to free tier',
        )
        parser.add_argument(
            '--list-free',
            action='store_true',
            help='List all users currently on the free tier',
        )

    def handle(self, *args, **options):
        if options['list_free']:
            from UserAPI.subscription import list_free_users
            from UserAPI.models import SubscriptionTier

            free_users = list_free_users()
            self.stdout.write(f"Found {len(free_users)} free-tier user(s):")
            for u in free_users:
                self.stdout.write(f"  - {u['email']} (joined: {u['date_joined'].strftime('%Y-%m-%d')})")
            return

        email = options['email']
        if not email:
            self.stderr.write(self.style.ERROR("Please provide --email"))
            return

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"User with email '{email}' does not exist."))
            self.stdout.write("Available users:")
            for u in User.objects.all():
                self.stdout.write(f"  - {u.email} (id={u.id})")
            return

        if options['deactivate']:
            from UserAPI.subscription import deactivate_premium_for_user
            success, message = deactivate_premium_for_user(user)
            if success:
                self.stdout.write(self.style.SUCCESS(message))
            else:
                self.stderr.write(self.style.ERROR(message))
            return

        from UserAPI.subscription import activate_premium_for_user

        # Determine duration
        if options['lifetime']:
            duration_days = None
        elif options['days']:
            duration_days = options['days']
        else:
            duration_days = None  # default to lifetime

        duration_label = f"{duration_days} days" if duration_days else "lifetime"
        self.stdout.write(f"Activating {duration_label} premium for {email}...")

        success, message = activate_premium_for_user(user, duration_days=duration_days)
        if success:
            self.stdout.write(self.style.SUCCESS(message))
        else:
            self.stderr.write(self.style.ERROR(message))
