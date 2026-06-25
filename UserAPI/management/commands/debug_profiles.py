from django.core.management.base import BaseCommand
from UserAPI.models import CustomUser, IndividualUser, BusinessUser

class Command(BaseCommand):
    help = 'Debug user profiles'

    def handle(self, *args, **options):
        self.stdout.write('=== User Profile Debug ===')
        
        for user in CustomUser.objects.all():
            self.stdout.write(f'\nUser: {user.email} (ID: {user.id})')
            self.stdout.write(f'  Username: {user.username}')
            
            # Check for individual profile
            if hasattr(user, 'individual_profile'):
                try:
                    individual = user.individual_profile
                    self.stdout.write(f'  Individual Profile: {individual.name}')
                except Exception as e:
                    self.stdout.write(f'  Individual Profile Error: {e}')
            else:
                self.stdout.write('  No individual_profile attribute')
            
            # Check for business profile
            if hasattr(user, 'business_profile'):
                try:
                    business = user.business_profile
                    self.stdout.write(f'  Business Profile: {business.name} - {business.company_name}')
                except Exception as e:
                    self.stdout.write(f'  Business Profile Error: {e}')
            else:
                self.stdout.write('  No business_profile attribute')
        
        self.stdout.write('\n=== All Individual Profiles ===')
        for individual in IndividualUser.objects.all():
            self.stdout.write(f'Individual: {individual.name} (User: {individual.user.email})')
        
        self.stdout.write('\n=== All Business Profiles ===')
        for business in BusinessUser.objects.all():
            self.stdout.write(f'Business: {business.name} - {business.company_name} (User: {business.user.email})')