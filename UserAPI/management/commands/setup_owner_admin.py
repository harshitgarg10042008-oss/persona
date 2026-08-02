"""
Set up the SUBSCRIPTION_OWNER_EMAILS account as a Django superuser (admin).

This command:
1. Finds the first email in SUBSCRIPTION_OWNER_EMAILS from .env
2. Marks that user as is_staff=True and is_superuser=True
3. Creates a SubscriptionTier with lifetime Premium
4. Creates an IndividualUser profile if missing

Usage:
    python manage.py setup_owner_admin
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


class Command(BaseCommand):
    help = 'Set up the owner account as Django superuser with lifetime Premium'

    def handle(self, *args, **options):
        owner_emails = getattr(settings, 'SUBSCRIPTION_OWNER_EMAILS', [])

        if not owner_emails:
            self.stderr.write(self.style.ERROR(
                "SUBSCRIPTION_OWNER_EMAILS is not configured in .env\n"
                "Add this line to your .env file:\n"
                "    SUBSCRIPTION_OWNER_EMAILS=your_email@example.com\n"
                "\n"
                "Then run this command again."
            ))
            return

        email = owner_emails[0]
        self.stdout.write(f"Configured owner email: {email}")

        # Find or create the user
        try:
            user = User.objects.get(email=email)
            self.stdout.write(f"Found existing user: {user.email}")
        except User.DoesNotExist:
            self.stdout.write(self.style.WARNING(
                f"No account found for {email}. You need to sign up first, "
                f"then run this command again."
            ))
            return

        # Make superuser (admin panel access)
        changed = False
        if not user.is_staff:
            user.is_staff = True
            changed = True
        if not user.is_superuser:
            user.is_superuser = True
            changed = True

        if changed:
            user.save()
            self.stdout.write(self.style.SUCCESS(
                f"User {email} is now a Django superuser — full admin access at /admin/"
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"User {email} is already a superuser."
            ))

        # Ensure lifetime Premium subscription
        from UserAPI.models import SubscriptionTier
        try:
            sub = user.subscription
            if sub.tier != 'premium':
                sub.tier = 'premium'
                sub.is_active = True
                sub.premium_expires_at = None
                sub.save()
                self.stdout.write(self.style.SUCCESS("Subscription set to lifetime Premium."))
            else:
                self.stdout.write(self.style.SUCCESS("Already has Premium tier."))
        except SubscriptionTier.DoesNotExist:
            SubscriptionTier.objects.create(
                user=user,
                tier='premium',
                is_active=True,
                premium_expires_at=None,
            )
            self.stdout.write(self.style.SUCCESS("Created lifetime Premium subscription."))

        # Ensure IndividualUser profile exists
        from UserAPI.models import IndividualUser
        if not hasattr(user, 'individual_profile'):
            name = user.first_name or user.username
            IndividualUser.objects.create(
                user=user,
                name=name,
            )
            self.stdout.write(self.style.SUCCESS(f"Created IndividualUser profile for {email}."))
        else:
            self.stdout.write("IndividualUser profile already exists.")

        # Summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("OWNER ADMIN SETUP COMPLETE"))
        self.stdout.write("=" * 60)
        self.stdout.write(f"  Email:      {user.email}")
        self.stdout.write(f"  is_staff:   {user.is_staff}")
        self.stdout.write(f"  is_super:   {user.is_superuser}")
        sub = user.subscription
        self.stdout.write(f"  Tier:       {sub.tier}")
        self.stdout.write(f"  Premium:    {sub.is_premium}")
        self.stdout.write(f"  Expires:    {sub.premium_expires_at or 'LIFETIME'}")
        self.stdout.write("\n" + self.style.SUCCESS(
            f"Go to http://127.0.0.1:8000/admin/ and log in with your credentials."
        ))
