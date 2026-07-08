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
