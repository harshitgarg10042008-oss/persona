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
