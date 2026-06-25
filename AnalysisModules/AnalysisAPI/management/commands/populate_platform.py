from django.core.management.base import BaseCommand
from AnalysisAPI.models import PlatformJobTitle, PlatformQuestion

class Command(BaseCommand):
    help = 'Populate platform with sample job titles and questions for testing'

    def handle(self, *args, **options):
        self.stdout.write('Creating sample job titles and questions...')
        
        # Create job titles with questions
        job_data = [
            {
                'title': 'Software Engineer',
                'description': 'Full-stack software development role with focus on web applications',
                'category': 'engineering',
                'questions': [
                    "Tell me about yourself and your background in software development.",
                    "Describe a challenging project you worked on and how you overcame obstacles.",
                    "How do you approach debugging and troubleshooting complex issues?",
                    "What programming languages and frameworks are you most comfortable with?",
                    "How do you stay updated with new technologies and industry trends?"
                ]
            },
            {
                'title': 'Marketing Manager',
                'description': 'Strategic marketing role focused on brand growth and digital campaigns',
                'category': 'marketing',
                'questions': [
                    "Walk me through your marketing experience and key achievements.",
                    "How do you develop and execute successful marketing campaigns?",
                    "Describe a time when a marketing strategy didn't work as planned. What did you learn?",
                    "How do you measure the success of marketing initiatives?",
                    "What digital marketing trends do you think will be most important this year?"
                ]
            },
            {
                'title': 'Sales Representative',
                'description': 'Customer-facing sales role with targets and relationship building',
                'category': 'sales',
                'questions': [
                    "Tell me about your sales experience and your greatest achievements.",
                    "How do you handle rejection and maintain motivation in sales?",
                    "Describe your approach to building relationships with potential clients.",
                    "Walk me through your typical sales process from lead to close.",
                    "How do you handle difficult customers or objections?"
                ]
            },
            {
                'title': 'Data Analyst',
                'description': 'Analytical role focusing on data insights and business intelligence',
                'category': 'analytics',
                'questions': [
                    "Describe your experience with data analysis and the tools you use.",
                    "How do you approach a new dataset and identify key insights?",
                    "Tell me about a time when your analysis led to important business decisions.",
                    "How do you ensure data quality and accuracy in your work?",
                    "What statistical methods do you find most useful in your analysis?"
                ]
            },
            {
                'title': 'Project Manager',
                'description': 'Leadership role coordinating teams and delivering projects on time',
                'category': 'management',
                'questions': [
                    "Tell me about your project management experience and methodology preferences.",
                    "How do you handle conflicting priorities and tight deadlines?",
                    "Describe a project that didn't go as planned. How did you recover?",
                    "How do you motivate team members and ensure collaboration?",
                    "What tools and techniques do you use to track project progress?"
                ]
            }
        ]
        
        created_jobs = 0
        created_questions = 0
        
        for job_info in job_data:
            # Create or get job title
            job_title, created = PlatformJobTitle.objects.get_or_create(
                title=job_info['title'],
                defaults={
                    'description': job_info['description'],
                    'category': job_info['category'],
                    'is_active': True
                }
            )
            
            if created:
                created_jobs += 1
                self.stdout.write(f"Created job title: {job_title.title}")
            
            # Create questions for this job title
            for i, question_text in enumerate(job_info['questions'], 1):
                question, created = PlatformQuestion.objects.get_or_create(
                    job_title=job_title,
                    question_text=question_text,
                    defaults={
                        'order': i,
                        'is_active': True
                    }
                )
                
                if created:
                    created_questions += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully created {created_jobs} job titles and {created_questions} questions'
            )
        )
        
        # Show summary
        total_jobs = PlatformJobTitle.objects.count()
        total_questions = PlatformQuestion.objects.count()
        
        self.stdout.write(f"Total job titles in system: {total_jobs}")
        self.stdout.write(f"Total questions in system: {total_questions}")