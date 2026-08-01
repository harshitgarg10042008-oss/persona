"""
Run this directly from PowerShell to:
1. Delete ALL other users (keep only harshit77.edu@gmail.com)
2. Delete ALL old assessments for that account
3. Set the account to lifetime Premium
4. Print final state

Usage:
    python manage.py fix_my_account
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()
OWNER_EMAIL = 'harshit77.edu@gmail.com'


class Command(BaseCommand):
    help = 'Clean database: keep only owner account, delete old assessments, set premium'

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("STEP 1: Clean up users")
        self.stdout.write("=" * 60)

        # Find the owner
        try:
            owner = User.objects.get(email=OWNER_EMAIL)
            self.stdout.write(self.style.SUCCESS(f"Owner found: {owner.email} (id={owner.id})"))
        except User.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Owner account {OWNER_EMAIL} does not exist!"))
            self.stdout.write("Available users:")
            for u in User.objects.all():
                self.stdout.write(f"  - {u.email} (id={u.id})")
            return

        # Delete all other users
        others = User.objects.exclude(email=OWNER_EMAIL)
        count = others.count()
        if count > 0:
            for u in others:
                self.stdout.write(f"  Deleting: {u.email}")
                u.delete()
            self.stdout.write(self.style.SUCCESS(f"Deleted {count} other user(s). Only {OWNER_EMAIL} remains."))
        else:
            self.stdout.write(self.style.SUCCESS("No other users to delete."))

        # List all remaining users
        self.stdout.write("\nRemaining users:")
        for u in User.objects.all():
            self.stdout.write(f"  - {u.email} (id={u.id})")

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("STEP 2: Delete all old assessments")
        self.stdout.write("=" * 60)

        from AnalysisAPI.models import IndividualAssessment, AssessmentSnapshot
        from django.contrib.auth import get_user_model
        User = get_user_model()
        owner = User.objects.get(email=OWNER_EMAIL)

        # Delete snapshots first (foreign key dependency)
        snapshots_deleted = AssessmentSnapshot.objects.filter(assessment__user=owner).count()
        AssessmentSnapshot.objects.filter(assessment__user=owner).delete()
        self.stdout.write(f"  Deleted {snapshots_deleted} assessment snapshots.")

        # Delete assessments
        assessments_deleted = IndividualAssessment.objects.filter(user=owner).count()
        IndividualAssessment.objects.filter(user=owner).delete()
        self.stdout.write(f"  Deleted {assessments_deleted} assessments.")

        self.stdout.write(self.style.SUCCESS(f"All old assessment data wiped for {OWNER_EMAIL}."))

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("STEP 3: Set lifetime Premium")
        self.stdout.write("=" * 60)

        from UserAPI.models import SubscriptionTier

        try:
            sub = owner.subscription
            sub.tier = 'premium'
            sub.is_active = True
            sub.premium_expires_at = None  # lifetime
            sub.save()
            self.stdout.write(self.style.SUCCESS(f"{OWNER_EMAIL} set to lifetime Premium."))
        except SubscriptionTier.DoesNotExist:
            SubscriptionTier.objects.create(
                user=owner,
                tier='premium',
                is_active=True,
                premium_expires_at=None,
            )
            self.stdout.write(self.style.SUCCESS(f"Created lifetime Premium for {OWNER_EMAIL}."))

        # Verify
        sub = owner.subscription
        self.stdout.write(f"\nSubscription tier: {sub.tier}")
        self.stdout.write(f"Is premium: {sub.is_premium}")
        self.stdout.write(f"Expires at: {sub.premium_expires_at or 'LIFETIME'}")

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("FINAL STATE")
        self.stdout.write("=" * 60)
        self.stdout.write(f"Users in DB: {User.objects.count()}")
        for u in User.objects.all():
            self.stdout.write(f"  - {u.email} (tier: {u.subscription.tier if hasattr(u, 'subscription') else 'unknown'})")
        self.stdout.write(f"Assessments: {IndividualAssessment.objects.count()}")
        self.stdout.write(self.style.SUCCESS("\nDONE! Dashboard will now show 0/0 with clean data."))
