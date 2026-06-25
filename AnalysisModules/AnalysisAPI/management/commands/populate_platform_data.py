"""
Django management command to populate platform job titles and questions
Run with: python manage.py populate_platform_data
"""

from django.core.management.base import BaseCommand
from AnalysisAPI.models import PlatformJobTitle, PlatformQuestion


class Command(BaseCommand):
    help = 'Populate platform job titles and questions for individual assessments'

    def handle(self, *args, **options):
        self.stdout.write('Creating platform job titles and questions...')
        
        # Software Engineer
        se_title, created = PlatformJobTitle.objects.get_or_create(
            title="Software Engineer",
            defaults={
                'description': "Design, develop, and maintain software applications and systems.",
                'category': 'technology',
                'is_active': True
            }
        )
        
        if created:
            # Mandatory questions for Software Engineer
            PlatformQuestion.objects.get_or_create(
                job_title=se_title,
                question_text="Tell me about yourself and your background in software development.",
                defaults={
                    'question_type': 'general',
                    'difficulty_level': 'easy',
                    'is_mandatory': True,
                    'expected_duration': 120,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=se_title,
                question_text="Describe a challenging technical problem you solved and your approach.",
                defaults={
                    'question_type': 'technical',
                    'difficulty_level': 'intermediate',
                    'is_mandatory': True,
                    'expected_duration': 180,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=se_title,
                question_text="How do you stay updated with new technologies and programming trends?",
                defaults={
                    'question_type': 'general',
                    'difficulty_level': 'easy',
                    'is_mandatory': True,
                    'expected_duration': 120,
                    'is_active': True
                }
            )
            
            # Optional questions for Software Engineer
            PlatformQuestion.objects.get_or_create(
                job_title=se_title,
                question_text="Explain the difference between SQL and NoSQL databases.",
                defaults={
                    'question_type': 'technical',
                    'difficulty_level': 'intermediate',
                    'is_mandatory': False,
                    'expected_duration': 150,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=se_title,
                question_text="How would you optimize a slow-performing web application?",
                defaults={
                    'question_type': 'technical',
                    'difficulty_level': 'hard',
                    'is_mandatory': False,
                    'expected_duration': 200,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=se_title,
                question_text="Describe your experience with version control systems like Git.",
                defaults={
                    'question_type': 'technical',
                    'difficulty_level': 'easy',
                    'is_mandatory': False,
                    'expected_duration': 120,
                    'is_active': True
                }
            )
        
        # Marketing Manager
        mm_title, created = PlatformJobTitle.objects.get_or_create(
            title="Marketing Manager",
            defaults={
                'description': "Develop and execute marketing strategies to promote products and services.",
                'category': 'marketing',
                'is_active': True
            }
        )
        
        if created:
            # Mandatory questions for Marketing Manager
            PlatformQuestion.objects.get_or_create(
                job_title=mm_title,
                question_text="Tell me about your marketing background and key achievements.",
                defaults={
                    'question_type': 'general',
                    'difficulty_level': 'easy',
                    'is_mandatory': True,
                    'expected_duration': 120,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=mm_title,
                question_text="How do you develop and execute a marketing strategy for a new product?",
                defaults={
                    'question_type': 'behavioral',
                    'difficulty_level': 'intermediate',
                    'is_mandatory': True,
                    'expected_duration': 180,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=mm_title,
                question_text="Describe a successful marketing campaign you managed.",
                defaults={
                    'question_type': 'behavioral',
                    'difficulty_level': 'intermediate',
                    'is_mandatory': True,
                    'expected_duration': 150,
                    'is_active': True
                }
            )
            
            # Optional questions for Marketing Manager
            PlatformQuestion.objects.get_or_create(
                job_title=mm_title,
                question_text="How do you measure the ROI of marketing campaigns?",
                defaults={
                    'question_type': 'technical',
                    'difficulty_level': 'intermediate',
                    'is_mandatory': False,
                    'expected_duration': 150,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=mm_title,
                question_text="What digital marketing tools and platforms are you familiar with?",
                defaults={
                    'question_type': 'technical',
                    'difficulty_level': 'easy',
                    'is_mandatory': False,
                    'expected_duration': 120,
                    'is_active': True
                }
            )
        
        # Sales Representative
        sr_title, created = PlatformJobTitle.objects.get_or_create(
            title="Sales Representative",
            defaults={
                'description': "Build relationships with clients and drive sales growth.",
                'category': 'sales',
                'is_active': True
            }
        )
        
        if created:
            # Mandatory questions for Sales Representative
            PlatformQuestion.objects.get_or_create(
                job_title=sr_title,
                question_text="Tell me about your sales experience and biggest achievements.",
                defaults={
                    'question_type': 'general',
                    'difficulty_level': 'easy',
                    'is_mandatory': True,
                    'expected_duration': 120,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=sr_title,
                question_text="How do you approach building relationships with new clients?",
                defaults={
                    'question_type': 'behavioral',
                    'difficulty_level': 'intermediate',
                    'is_mandatory': True,
                    'expected_duration': 150,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=sr_title,
                question_text="Describe a challenging sale you closed and your strategy.",
                defaults={
                    'question_type': 'behavioral',
                    'difficulty_level': 'intermediate',
                    'is_mandatory': True,
                    'expected_duration': 180,
                    'is_active': True
                }
            )
            
            # Optional questions for Sales Representative
            PlatformQuestion.objects.get_or_create(
                job_title=sr_title,
                question_text="How do you handle rejection and maintain motivation?",
                defaults={
                    'question_type': 'behavioral',
                    'difficulty_level': 'easy',
                    'is_mandatory': False,
                    'expected_duration': 120,
                    'is_active': True
                }
            )
            
            PlatformQuestion.objects.get_or_create(
                job_title=sr_title,
                question_text="What CRM tools have you used to manage your sales pipeline?",
                defaults={
                    'question_type': 'technical',
                    'difficulty_level': 'easy',
                    'is_mandatory': False,
                    'expected_duration': 90,
                    'is_active': True
                }
            )
        
        self.stdout.write(
            self.style.SUCCESS('Successfully populated platform job titles and questions!')
        )
        
        # Print summary
        job_titles = PlatformJobTitle.objects.count()
        questions = PlatformQuestion.objects.count()
        
        self.stdout.write(f'Created {job_titles} job titles with {questions} total questions.')