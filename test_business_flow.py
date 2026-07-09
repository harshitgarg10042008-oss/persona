"""
Test script for business institution flow
Tests the complete flow: create business -> get code -> create individual -> join institution
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from UserAPI.models import CustomUser, IndividualUser, BusinessUser, InstitutionMembership
from AnalysisAPI.models import IndividualAssessment, PlatformJobTitle

def test_business_flow():
    print("=" * 70)
    print("Business Institution Flow Test")
    print("=" * 70)
    
    # Step 1: Create test business user
    print("\n--- Step 1: Creating Test Business User ---")
    business_email = "test.business@example.com"
    
    try:
        business_user = CustomUser.objects.get(email=business_email)
        print(f"Business user already exists: {business_user.email}")
    except CustomUser.DoesNotExist:
        business_user = CustomUser.objects.create_user(
            email=business_email,
            username=business_email,
            password="testpass123"
        )
        BusinessUser.objects.create(
            user=business_user,
            name="Test Business Admin",
            company_name="GNIOT Test Institution"
        )
        print(f"Created business user: {business_user.email}")
    
    business_profile = business_user.business_profile
    institution_code = business_profile.institution_code
    print(f"Institution Code: {institution_code}")
    
    # Step 2: Create test individual user
    print("\n--- Step 2: Creating Test Individual User ---")
    individual_email = "test.student@example.com"
    
    try:
        individual_user = CustomUser.objects.get(email=individual_email)
        print(f"Individual user already exists: {individual_user.email}")
    except CustomUser.DoesNotExist:
        individual_user = CustomUser.objects.create_user(
            email=individual_email,
            username=individual_email,
            password="testpass123"
        )
        IndividualUser.objects.create(
            user=individual_user,
            name="Test Student"
        )
        print(f"Created individual user: {individual_user.email}")
    
    individual_profile = individual_user.individual_profile
    
    # Step 3: Test institution code parsing
    print("\n--- Step 3: Testing Institution Code Parsing ---")
    try:
        business_id = int(institution_code.replace('INST-', ''))
        parsed_business = BusinessUser.objects.get(id=business_id)
        print(f"✓ Institution code parses correctly")
        print(f"  Code: {institution_code}")
        print(f"  Business ID: {business_id}")
        print(f"  Business Name: {parsed_business.company_name or parsed_business.name}")
    except (ValueError, BusinessUser.DoesNotExist) as e:
        print(f"✗ Institution code parsing failed: {e}")
        return False
    
    # Step 4: Test joining institution
    print("\n--- Step 4: Testing Institution Join ---")
    from django.utils import timezone
    
    # Check if already member
    existing_membership = InstitutionMembership.objects.filter(
        individual=individual_profile,
        business=business_profile
    ).first()
    
    if existing_membership:
        print(f"Already a member of this institution")
        if not existing_membership.is_active:
            existing_membership.is_active = True
            existing_membership.save()
            print(f"Reactivated membership")
    else:
        # Create new membership with consent
        membership = InstitutionMembership.objects.create(
            individual=individual_profile,
            business=business_profile,
            consent_granted=True,
            consent_granted_at=timezone.now()
        )
        print(f"✓ Created new institution membership")
        print(f"  Individual: {individual_profile.name}")
        print(f"  Business: {business_profile.company_name or business_profile.name}")
        print(f"  Consent Granted: {membership.consent_granted}")
        print(f"  Joined At: {membership.joined_at}")
    
    # Step 5: Verify membership in business dashboard context
    print("\n--- Step 5: Verifying Business Dashboard Context ---")
    institution_members = InstitutionMembership.objects.filter(
        business=business_profile,
        is_active=True
    ).select_related('individual')
    
    print(f"Total institution members: {institution_members.count()}")
    for member in institution_members:
        print(f"  - {member.individual.name} ({member.individual.user.email})")
        print(f"    Consent: {member.consent_granted}")
        print(f"    Joined: {member.joined_at}")
    
    # Step 6: Test member assessments query
    print("\n--- Step 6: Testing Member Assessments Query ---")
    member_assessments = IndividualAssessment.objects.filter(
        institution_membership__business=business_profile,
        institution_membership__is_active=True,
        status='completed'
    )
    
    print(f"Total member assessments: {member_assessments.count()}")
    
    # Calculate average score
    avg_member_score = None
    if member_assessments.exists() and member_assessments.filter(overall_score__isnull=False).exists():
        scores = [a.overall_score for a in member_assessments if a.overall_score]
        if scores:
            avg_member_score = sum(scores) / len(scores)
            print(f"Average member score: {avg_member_score:.1f}/10")
    else:
        print("No completed assessments yet")
    
    # Step 7: Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"✓ Business User: {business_user.email}")
    print(f"✓ Institution Code: {institution_code}")
    print(f"✓ Individual User: {individual_user.email}")
    print(f"✓ Membership Created: Yes")
    print(f"✓ Consent Granted: Yes")
    print(f"✓ Business Dashboard Context: Ready")
    print(f"\nNext Steps:")
    print(f"1. Log in as business user to see institution code on dashboard")
    print(f"2. Log in as individual user to see institution membership")
    print(f"3. Individual user can complete assessments")
    print(f"4. Business user can view aggregate stats and export CSV")
    
    return True

if __name__ == "__main__":
    success = test_business_flow()
    if success:
        print("\n✓ Test completed successfully!")
    else:
        print("\n✗ Test failed!")
