"""
Management command to:
1. Delete all CustomUser accounts except the owner (harshit77.edu@gmail.com)
2. Ensure the owner has a SubscriptionTier with tier='premium' and is_active=True

Usage:
    python manage.py clean_users_and_set_premium
    python manage.py clean_users_and_set_premium --dry-run
    python manage.py clean_users_and_set_premium --owner-email admin@example.com
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Delete all users except the owner and ensure owner has premium tier"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without actually deleting',
        )
        parser.add_argument(
            '--owner-email',
            default='harshit77.edu@gmail.com',
            help='Email of the owner account to keep (default: harshit77.edu@gmail.com)',
        )

    def handle(self, *args, **options):
        owner_email = options['owner_email']
        dry_run = options['dry_run']

        self.stdout.write(f"Owner email: {owner_email}")

        # Find the owner
        try:
            owner = User.objects.get(email=owner_email)
            self.stdout.write(f"Found owner: {owner.email} (username: {owner.username})")
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Owner account with email '{owner_email}' does not exist!"))
            self.stdout.write("Available users:")
            for u in User.objects.all():
                self.stdout.write(f"  - {u.email} (id={u.id})")
            return

        # Get all users except owner
        users_to_delete = User.objects.exclude(email=owner_email)
        count = users_to_delete.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS("No other users to delete."))
        else:
            if dry_run:
                self.stdout.write(f"Would delete {count} user(s):")
                for u in users_to_delete:
                    self.stdout.write(f"  - {u.email} (id={u.id})")
            else:
                self.stdout.write(f"Deleting {count} user(s)...")
                for u in users_to_delete:
                    self.stdout.write(f"  Deleting: {u.email} (id={u.id})")
                    u.delete()
                self.stdout.write(self.style.SUCCESS(f"Successfully deleted {count} user(s)."))

        # Now ensure owner has a premium SubscriptionTier
        from UserAPI.models import SubscriptionTier

        try:
            sub = owner.subscription
            if sub.tier != 'premium':
                sub.tier = 'premium'
                sub.is_active = True
                sub.premium_expires_at = None  # lifetime premium for owner
                sub.save()
                self.stdout.write(self.style.SUCCESS(f"Updated {owner.email}'s tier to premium (lifetime)."))
            else:
                self.stdout.write(self.style.SUCCESS(f"{owner.email} already has premium tier."))
        except SubscriptionTier.DoesNotExist:
            SubscriptionTier.objects.create(
                user=owner,
                tier='premium',
                is_active=True,
                premium_expires_at=None,  # lifetime
            )
            self.stdout.write(self.style.SUCCESS(f"Created premium SubscriptionTier for {owner.email}."))

        # Ensure owner emails are in settings
        self.stdout.write("")
        self.stdout.write(self.style.WARNING(
            "IMPORTANT: Make sure SUBSCRIPTION_OWNER_EMAILS in settings/.env includes "
            f"'{owner_email}' so the owner bypasses all gating checks."
        ))
        self.stdout.write(self.style.SUCCESS("Done!"))
