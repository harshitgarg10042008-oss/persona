from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from datetime import timedelta

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

class IndividualUser(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='individual_profile')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Streak tracking
    current_streak = models.PositiveIntegerField(default=0, help_text="Current consecutive days of practice")
    longest_streak = models.PositiveIntegerField(default=0, help_text="Longest streak achieved")
    last_activity_date = models.DateField(null=True, blank=True, help_text="Date of last completed assessment")
    
    # Media retention settings
    media_retention_days = models.PositiveIntegerField(
        default=30,
        choices=[(15, '15 days'), (30, '30 days'), (60, '60 days')],
        help_text="How long to keep interview recordings before automatic deletion"
    )
    
    # Video recording consent
    video_consent_given_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when user consented to video recording and analysis"
    )
    
    def update_streak(self):
        """Update streak based on assessment completion"""
        today = timezone.now().date()
        
        if self.last_activity_date is None:
            # First assessment
            self.current_streak = 1
            self.longest_streak = 1
            self.last_activity_date = today
        elif self.last_activity_date == today:
            # Already completed an assessment today, no change
            pass
        elif self.last_activity_date == today - timedelta(days=1):
            # Consecutive day, increment streak
            self.current_streak += 1
            self.last_activity_date = today
            if self.current_streak > self.longest_streak:
                self.longest_streak = self.current_streak
        else:
            # Streak broken, reset to 1
            self.current_streak = 1
            self.last_activity_date = today
        
        self.save()
    
    def __str__(self):
        return f"{self.name} - Individual"

class BusinessUser(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='business_profile')
    name = models.CharField(max_length=100)
    company_name = models.CharField(max_length=200, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.name} - Business"
    
    @property
    def institution_code(self):
        """Generate a unique institution code for sharing"""
        return f"INST-{self.id:06d}"

class InstitutionMembership(models.Model):
    """Track individual users' membership in institutions"""
    individual = models.ForeignKey(IndividualUser, on_delete=models.CASCADE, related_name='institution_memberships')
    business = models.ForeignKey(BusinessUser, on_delete=models.CASCADE, related_name='member_individuals')
    
    # Privacy consent tracking
    consent_granted = models.BooleanField(default=False, help_text="User consented to share results with institution")
    consent_granted_at = models.DateTimeField(null=True, blank=True)
    
    # Membership details
    joined_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        unique_together = ['individual', 'business']
    
    def __str__(self):
        return f"{self.individual.name} - {self.business.company_name or self.business.name}"

class UserInterviewerPreference(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='interviewer_preference')
    persona_id = models.CharField(max_length=50, default='friendly_encouraging')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.persona_id}"
class Institution(models.Model):
    """B2B Institution account — universities, colleges, training providers."""
    PLAN_CHOICES = [
        ('monthly', 'Monthly'),
        ('annual', 'Annual'),
        ('enterprise', 'Enterprise'),
    ]
    name = models.CharField(max_length=255)
    contact_email = models.EmailField()
    plan = models.CharField(max_length=20, choices=PLAN_CHOICES, default='monthly')
    seat_limit = models.IntegerField(
        null=True, blank=True,
        help_text='Max linked students. NULL = unlimited.'
    )
    subscription_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Institutions'
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def is_active(self):
        if not self.subscription_expires_at:
            return True
        return self.subscription_expires_at > timezone.now()

    @property
    def has_unlimited_seats(self):
        return self.seat_limit is None

    def current_seat_count(self):
        """Return number of active institution_member subscriptions."""
        return SubscriptionTier.objects.filter(
            institution=self,
            tier='institution_member',
            is_active=True
        ).count()

    def can_add_member(self):
        """Check if institution can add another member."""
        if self.seat_limit is None:
            return True  # unlimited
        return self.current_seat_count() < self.seat_limit


class SubscriptionTier(models.Model):
    """One-to-one tier assignment per user. Controls feature gating."""
    TIER_CHOICES = [
        ('free', 'Free'),
        ('premium', 'Premium'),
        ('institution_member', 'Institution Member'),
    ]
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name='subscription')
    tier = models.CharField(max_length=20, choices=TIER_CHOICES, default='free')
    premium_expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When premium expires. NULL = free tier or lifetime premium.'
    )
    institution = models.ForeignKey(
        Institution, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='member_subscriptions'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Subscription Tier'
        verbose_name_plural = 'Subscription Tiers'

    def __str__(self):
        return f"{self.user.email} — {self.get_tier_display()}"

    @property
    def is_premium(self):
        """Premium if tier is premium (and not expired) or institution_member."""
        if self.tier == 'institution_member':
            return self.is_active and self.institution and self.institution.is_active
        if self.tier == 'premium':
            if not self.is_active:
                return False
            if self.premium_expires_at is None:
                return True  # lifetime premium
            return self.premium_expires_at > timezone.now()
        return False

    @property
    def is_free(self):
        return self.tier == 'free' or not self.is_premium

    @property
    def is_in_premium_period(self):
        """Alias for is_premium — kept for backward compatibility."""
        return self.is_premium

    @property
    def is_institution_member(self):
        return self.tier == 'institution_member'
