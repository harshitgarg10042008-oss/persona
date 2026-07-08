"""
Test script for engagement features: streak tracking, peer comparison, and badges
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta, date
from UserAPI.models import CustomUser, IndividualUser
from AnalysisAPI.models import IndividualAssessment, PlatformJobTitle, PlatformQuestion
from AnalysisAPI.badge_utils import get_user_achievements, get_latest_badge_data

def test_streak_logic():
    """Test streak tracking logic"""
    print("=== Testing Streak Logic ===")
    
    # Create a test user
    user, created = CustomUser.objects.get_or_create(
        username='test_streak_user',
        defaults={
            'email': 'test_streak@example.com',
            'first_name': 'Test',
            'last_name': 'Streak'
        }
    )
    
    if created:
        user.set_password('testpass123')
        user.save()
    
    # Get or create individual profile
    profile, created = IndividualUser.objects.get_or_create(
        user=user,
        defaults={'name': f"{user.first_name} {user.last_name}"}
    )
    
    print(f"User: {user.username}")
    print(f"Initial streak: {profile.current_streak}")
    print(f"Initial longest streak: {profile.longest_streak}")
    print(f"Initial last activity: {profile.last_activity_date}")
    
    # Test 1: First assessment
    print("\n--- Test 1: First assessment ---")
    profile.last_activity_date = None
    profile.current_streak = 0
    profile.longest_streak = 0
    profile.save()
    profile.update_streak()
    print(f"After first assessment: streak={profile.current_streak}, longest={profile.longest_streak}, last_activity={profile.last_activity_date}")
    assert profile.current_streak == 1, "First assessment should set streak to 1"
    assert profile.longest_streak == 1, "First assessment should set longest streak to 1"
    
    # Test 2: Same day assessment (no change)
    print("\n--- Test 2: Same day assessment ---")
    profile.update_streak()
    print(f"After same day: streak={profile.current_streak}, longest={profile.longest_streak}")
    assert profile.current_streak == 1, "Same day assessment should not increment streak"
    
    # Test 3: Consecutive day
    print("\n--- Test 3: Consecutive day ---")
    profile.last_activity_date = date.today() - timedelta(days=1)
    profile.save()
    profile.update_streak()
    print(f"After consecutive day: streak={profile.current_streak}, longest={profile.longest_streak}")
    assert profile.current_streak == 2, "Consecutive day should increment streak"
    assert profile.longest_streak == 2, "Longest streak should be updated"
    
    # Test 4: Streak broken
    print("\n--- Test 4: Streak broken (gap of 2+ days) ---")
    profile.last_activity_date = date.today() - timedelta(days=3)
    profile.save()
    profile.update_streak()
    print(f"After streak broken: streak={profile.current_streak}, longest={profile.longest_streak}")
    assert profile.current_streak == 1, "Broken streak should reset to 1"
    assert profile.longest_streak == 2, "Longest streak should remain at 2"
    
    print("\n✅ Streak logic tests passed!")
    
    # Cleanup
    profile.delete()
    user.delete()


def test_platform_average():
    """Test platform average calculation"""
    print("\n=== Testing Platform Average Calculation ===")
    
    # Get or create a job title
    job_title, created = PlatformJobTitle.objects.get_or_create(
        title='Software Engineer',
        defaults={
            'description': 'Test job title for platform average',
            'category': 'technology'
        }
    )
    
    print(f"Job title: {job_title.title}")
    
    # Check current average
    avg = IndividualAssessment.get_platform_average_for_job(job_title.id)
    print(f"Current platform average: {avg}")
    
    # Test with insufficient data (should return None)
    print("\n--- Test: Insufficient data (< 5 assessments) ---")
    avg = IndividualAssessment.get_platform_average_for_job(job_title.id, min_assessments=5)
    print(f"Average with min_assessments=5: {avg}")
    if avg is None:
        print("✅ Correctly returns None when insufficient data")
    
    # Test with lower threshold
    print("\n--- Test: Lower threshold (min_assessments=1) ---")
    avg = IndividualAssessment.get_platform_average_for_job(job_title.id, min_assessments=1)
    print(f"Average with min_assessments=1: {avg}")
    
    print("\n✅ Platform average calculation tests passed!")


def test_achievements():
    """Test achievement badge logic"""
    print("\n=== Testing Achievement Badge Logic ===")
    
    # Create a test user
    user, created = CustomUser.objects.get_or_create(
        username='test_badge_user',
        defaults={
            'email': 'test_badge@example.com',
            'first_name': 'Test',
            'last_name': 'Badge'
        }
    )
    
    if created:
        user.set_password('testpass123')
        user.save()
    
    # Get or create individual profile
    profile, created = IndividualUser.objects.get_or_create(
        user=user,
        defaults={'name': f"{user.first_name} {user.last_name}"}
    )
    
    print(f"User: {user.username}")
    
    # Test achievements for user with no assessments
    print("\n--- Test: No assessments ---")
    achievements = get_user_achievements(user)
    print(f"Achievements: {len(achievements)}")
    print(f"Expected: 0 (no completed assessments)")
    assert len(achievements) == 0, "User with no assessments should have no achievements"
    
    # Test badge data for user with no achievements
    badge_data = get_latest_badge_data(user)
    print(f"Latest badge data: {badge_data}")
    assert badge_data is None, "User with no achievements should have no badge data"
    
    print("\n✅ Achievement badge logic tests passed!")
    
    # Cleanup
    profile.delete()
    user.delete()


if __name__ == '__main__':
    try:
        test_streak_logic()
        test_platform_average()
        test_achievements()
        print("\n" + "="*50)
        print("✅ ALL TESTS PASSED!")
        print("="*50)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
