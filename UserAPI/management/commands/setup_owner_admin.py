import os

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings


class Command(BaseCommand):
    help = "Set up the owner account as Django superuser with lifetime Premium"

    def handle(self, *args, **options):
        User = get_user_model()

        owner_emails = getattr(settings, "SUBSCRIPTION_OWNER_EMAILS", [])

        if not owner_emails:
            self.stderr.write(
                self.style.ERROR(
                    "SUBSCRIPTION_OWNER_EMAILS is not configured."
                )
            )
            return

        email = owner_emails[0]
        self.stdout.write(f"Configured owner email: {email}")

        # Get password from environment
        password = os.environ.get("SUBSCRIPTION_OWNER_PASSWORD")

        if not password:
            self.stderr.write(
                self.style.ERROR(
                    "SUBSCRIPTION_OWNER_PASSWORD is not configured."
                )
            )
            return

        # Get username from environment, or use email prefix
        username = os.environ.get(
            "SUBSCRIPTION_OWNER_USERNAME",
            email.split("@")[0]
        )

        # Find or create the owner account
        try:
            user = User.objects.get(email=email)

            self.stdout.write(
                f"Found existing user: {user.email}"
            )

        except User.DoesNotExist:
            user = User.objects.create_superuser(
                email=email,
                username=username,
                password=password,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created owner account: {email}"
                )
            )

        # Make sure the account is a superuser
        changed = False

        if not user.is_staff:
            user.is_staff = True
            changed = True

        if not user.is_superuser:
            user.is_superuser = True
            changed = True

        if changed:
            user.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"{email} is now a Django superuser."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{email} is already a superuser."
                )
            )

        # Ensure lifetime Premium subscription
        from UserAPI.models import SubscriptionTier

        try:
            sub = user.subscription

            if sub.tier != "premium":
                sub.tier = "premium"
                sub.is_active = True
                sub.premium_expires_at = None
                sub.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        "Subscription set to lifetime Premium."
                    )
                )
            else:
                self.stdout.write(
                    "Already has Premium tier."
                )

        except SubscriptionTier.DoesNotExist:
            SubscriptionTier.objects.create(
                user=user,
                tier="premium",
                is_active=True,
                premium_expires_at=None,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    "Created lifetime Premium subscription."
                )
            )

        # Ensure IndividualUser profile exists
        from UserAPI.models import IndividualUser

        if not hasattr(user, "individual_profile"):
            name = user.first_name or user.username

            IndividualUser.objects.create(
                user=user,
                name=name,
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Created IndividualUser profile for {email}."
                )
            )
        else:
            self.stdout.write(
                "IndividualUser profile already exists."
            )

        # Final summary
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(
            self.style.SUCCESS("OWNER ADMIN SETUP COMPLETE")
        )
        self.stdout.write("=" * 60)

        self.stdout.write(f"  Email:    {user.email}")
        self.stdout.write(f"  is_staff: {user.is_staff}")
        self.stdout.write(f"  is_super: {user.is_superuser}")

        sub = user.subscription

        self.stdout.write(f"  Tier:     {sub.tier}")
        self.stdout.write(
            f"  Premium:  {sub.is_premium}"
        )
        self.stdout.write(
            f"  Expires:  {sub.premium_expires_at or 'LIFETIME'}"
        )