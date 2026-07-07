"""
Django management command to expand the platform question bank
Run with: python manage.py expand_question_bank
"""

from django.core.management.base import BaseCommand
from AnalysisAPI.models import PlatformJobTitle, PlatformQuestion


class Command(BaseCommand):
    help = 'Expand platform question bank with additional job roles and questions'

    def handle(self, *args, **options):
        self.stdout.write('Expanding platform question bank...')
        
        # ========================================
        # EXPAND EXISTING ROLES
        # ========================================
        
        # Data Analyst (expand from 15 to 25)
        da_title = PlatformJobTitle.objects.get(title="Data Analyst")
        self._add_data_analyst_questions(da_title)
        
        # Marketing Manager (expand from 10 to 20)
        mm_title = PlatformJobTitle.objects.get(title="Marketing Manager")
        self._add_marketing_manager_questions(mm_title)
        
        # Project Manager (expand from 5 to 20)
        pm_title = PlatformJobTitle.objects.get(title="Project Manager")
        self._add_project_manager_questions(pm_title)
        
        # Sales Representative (expand from 10 to 20)
        sr_title = PlatformJobTitle.objects.get(title="Sales Representative")
        self._add_sales_representative_questions(sr_title)
        
        # Software Engineer (expand from 10 to 25)
        se_title = PlatformJobTitle.objects.get(title="Software Engineer")
        self._add_software_engineer_questions(se_title)
        
        # Tester (expand from 2 to 20)
        tester_title = PlatformJobTitle.objects.get(title="Tester")
        self._add_tester_questions(tester_title)
        
        # ========================================
        # ADD NEW JOB ROLES
        # ========================================
        
        # Product Manager
        pm_new_title, created = PlatformJobTitle.objects.get_or_create(
            title="Product Manager",
            defaults={
                'description': "Lead product strategy, development, and lifecycle management.",
                'category': 'management',
                'is_active': True
            }
        )
        if created:
            self._add_product_manager_questions(pm_new_title)
        
        # HR Recruiter
        hr_title, created = PlatformJobTitle.objects.get_or_create(
            title="HR Recruiter",
            defaults={
                'description': "Manage talent acquisition and recruitment processes.",
                'category': 'hr',
                'is_active': True
            }
        )
        if created:
            self._add_hr_recruiter_questions(hr_title)
        
        # Business Analyst
        ba_title, created = PlatformJobTitle.objects.get_or_create(
            title="Business Analyst",
            defaults={
                'description': "Analyze business processes and requirements to drive improvements.",
                'category': 'analytics',
                'is_active': True
            }
        )
        if created:
            self._add_business_analyst_questions(ba_title)
        
        # Customer Support Specialist
        cs_title, created = PlatformJobTitle.objects.get_or_create(
            title="Customer Support Specialist",
            defaults={
                'description': "Provide exceptional customer service and resolve issues.",
                'category': 'operations',
                'is_active': True
            }
        )
        if created:
            self._add_customer_support_questions(cs_title)
        
        # UI/UX Designer
        ux_title, created = PlatformJobTitle.objects.get_or_create(
            title="UI/UX Designer",
            defaults={
                'description': "Design intuitive and visually appealing user interfaces and experiences.",
                'category': 'technology',
                'is_active': True
            }
        )
        if created:
            self._add_ui_ux_designer_questions(ux_title)
        
        # DevOps Engineer
        devops_title, created = PlatformJobTitle.objects.get_or_create(
            title="DevOps Engineer",
            defaults={
                'description': "Bridge development and operations to improve deployment and reliability.",
                'category': 'technology',
                'is_active': True
            }
        )
        if created:
            self._add_devops_engineer_questions(devops_title)
        
        self.stdout.write(
            self.style.SUCCESS('Successfully expanded platform question bank!')
        )
        
        # Print summary
        job_titles = PlatformJobTitle.objects.all().order_by('title')
        questions = PlatformQuestion.objects.count()
        
        self.stdout.write(f'\n{"="*80}')
        self.stdout.write(f'FINAL JOB ROLES AND QUESTION COUNTS')
        self.stdout.write(f'{"="*80}')
        self.stdout.write(f'\nTotal job roles: {job_titles.count()}')
        self.stdout.write(f'Total questions: {questions}')
        
        self.stdout.write(f'\n{"-"*80}')
        self.stdout.write(f'{"Job Title":<30} {"Category":<15} {"Questions":<10}')
        self.stdout.write(f'{"-"*80}')
        
        for jt in job_titles:
            question_count = jt.questions.count()
            self.stdout.write(f'{jt.title:<30} {jt.get_category_display():<15} {question_count:<10}')
        
        self.stdout.write(f'{"="*80}')

    def _create_question(self, job_title, question_text, question_type, difficulty, mandatory, duration):
        """Helper to create a question if it doesn't exist"""
        # Check if question already exists for this job title
        if not PlatformQuestion.objects.filter(job_title=job_title, question_text=question_text).exists():
            PlatformQuestion.objects.create(
                job_title=job_title,
                question_text=question_text,
                question_type=question_type,
                difficulty_level=difficulty,
                is_mandatory=mandatory,
                expected_duration=duration,
                is_active=True
            )

    def _add_data_analyst_questions(self, job_title):
        """Add additional questions for Data Analyst role"""
        questions = [
            ("What data visualization tools have you used and which do you prefer?", 'technical', 'intermediate', False, 120),
            ("How do you handle missing or inconsistent data in your analysis?", 'technical', 'intermediate', False, 150),
            ("Describe a time when your data analysis led to a significant business decision.", 'behavioral', 'intermediate', False, 180),
            ("How do you communicate complex data insights to non-technical stakeholders?", 'behavioral', 'intermediate', False, 150),
            ("What machine learning algorithms are you familiar with and when would you use them?", 'technical', 'hard', False, 180),
            ("How do you ensure data privacy and compliance in your work?", 'situational', 'intermediate', False, 150),
            ("Describe your experience with A/B testing and experimental design.", 'technical', 'intermediate', False, 150),
            ("How do you prioritize which data analysis projects to work on?", 'behavioral', 'intermediate', False, 120),
            ("What's your approach to cleaning and preparing large datasets?", 'technical', 'intermediate', False, 150),
            ("How do you validate your data analysis results?", 'technical', 'intermediate', False, 120),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_marketing_manager_questions(self, job_title):
        """Add additional questions for Marketing Manager role"""
        questions = [
            ("How do you identify and target your ideal customer segments?", 'behavioral', 'intermediate', False, 150),
            ("Describe your experience with content marketing and content strategy.", 'behavioral', 'intermediate', False, 150),
            ("How do you handle a marketing campaign that's not performing as expected?", 'situational', 'intermediate', False, 180),
            ("What's your approach to building and managing a marketing team?", 'behavioral', 'intermediate', False, 150),
            ("How do you stay competitive in a rapidly changing digital landscape?", 'behavioral', 'intermediate', False, 120),
            ("Describe your experience with influencer marketing and partnerships.", 'behavioral', 'intermediate', False, 150),
            ("How do you allocate budget across different marketing channels?", 'technical', 'intermediate', False, 150),
            ("What metrics do you track to measure brand awareness?", 'technical', 'intermediate', False, 120),
            ("How do you collaborate with sales teams to align marketing and sales goals?", 'behavioral', 'intermediate', False, 150),
            ("Describe a time you had to pivot your marketing strategy mid-campaign.", 'behavioral', 'hard', False, 180),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_project_manager_questions(self, job_title):
        """Add questions for Project Manager role"""
        questions = [
            ("Tell me about your project management experience and methodology.", 'general', 'easy', True, 120),
            ("How do you handle scope creep in a project?", 'situational', 'intermediate', True, 150),
            ("Describe your approach to risk management in projects.", 'behavioral', 'intermediate', True, 150),
            ("How do you manage conflicting priorities from stakeholders?", 'situational', 'intermediate', False, 150),
            ("What project management tools and methodologies are you familiar with?", 'technical', 'intermediate', False, 120),
            ("Describe a project that failed and what you learned from it.", 'behavioral', 'intermediate', False, 180),
            ("How do you estimate project timelines and manage deadlines?", 'technical', 'intermediate', False, 150),
            ("How do you motivate team members during challenging projects?", 'behavioral', 'intermediate', False, 150),
            ("Describe your experience with cross-functional team leadership.", 'behavioral', 'intermediate', False, 150),
            ("How do you communicate project status to executives and stakeholders?", 'behavioral', 'intermediate', False, 120),
            ("What's your approach to quality assurance in project delivery?", 'technical', 'intermediate', False, 120),
            ("How do you handle underperforming team members?", 'situational', 'hard', False, 180),
            ("Describe your experience with Agile vs. Waterfall methodologies.", 'technical', 'intermediate', False, 150),
            ("How do you manage remote or distributed project teams?", 'behavioral', 'intermediate', False, 150),
            ("What metrics do you use to measure project success?", 'technical', 'intermediate', False, 120),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_sales_representative_questions(self, job_title):
        """Add additional questions for Sales Representative role"""
        questions = [
            ("How do you research and prepare for sales calls?", 'behavioral', 'intermediate', False, 120),
            ("Describe your approach to negotiating pricing and contracts.", 'behavioral', 'intermediate', False, 150),
            ("How do you handle objections from potential customers?", 'situational', 'intermediate', False, 150),
            ("What's your strategy for upselling and cross-selling?", 'behavioral', 'intermediate', False, 120),
            ("How do you prioritize your sales pipeline?", 'technical', 'intermediate', False, 120),
            ("Describe a time you turned around a dissatisfied customer.", 'behavioral', 'intermediate', False, 180),
            ("How do you stay motivated during slow sales periods?", 'behavioral', 'easy', False, 120),
            ("What's your approach to cold calling and prospecting?", 'behavioral', 'intermediate', False, 150),
            ("How do you collaborate with other teams like marketing and product?", 'behavioral', 'intermediate', False, 120),
            ("Describe your most successful sales deal and what made it successful.", 'behavioral', 'intermediate', False, 180),
            ("How do you adapt your sales approach for different industries?", 'behavioral', 'intermediate', False, 120),
            ("What techniques do you use to build long-term customer relationships?", 'behavioral', 'intermediate', False, 150),
            ("How do you handle competitive pressure in your market?", 'situational', 'intermediate', False, 150),
            ("Describe your experience with consultative selling approaches.", 'behavioral', 'intermediate', False, 150),
            ("How do you forecast your sales performance accurately?", 'technical', 'intermediate', False, 120),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_software_engineer_questions(self, job_title):
        """Add additional questions for Software Engineer role"""
        questions = [
            ("Explain the concept of Big O notation and its importance.", 'technical', 'intermediate', False, 150),
            ("How do you handle technical debt in your codebase?", 'situational', 'intermediate', False, 150),
            ("Describe your experience with microservices architecture.", 'technical', 'intermediate', False, 180),
            ("How do you approach debugging complex issues?", 'behavioral', 'intermediate', False, 120),
            ("What's your experience with containerization (Docker, Kubernetes)?", 'technical', 'intermediate', False, 150),
            ("How do you write clean, maintainable code?", 'behavioral', 'intermediate', False, 120),
            ("Describe your experience with RESTful APIs and API design.", 'technical', 'intermediate', False, 150),
            ("How do you handle concurrent programming and race conditions?", 'technical', 'hard', False, 180),
            ("What's your approach to unit testing and test-driven development?", 'technical', 'intermediate', False, 150),
            ("How do you stay current with security best practices?", 'technical', 'intermediate', False, 120),
            ("Describe your experience with cloud platforms (AWS, GCP, Azure).", 'technical', 'intermediate', False, 150),
            ("How do you approach code reviews and giving feedback?", 'behavioral', 'intermediate', False, 120),
            ("What's your experience with frontend frameworks (React, Vue, Angular)?", 'technical', 'intermediate', False, 150),
            ("How do you optimize database queries for performance?", 'technical', 'intermediate', False, 150),
            ("Describe a time you had to learn a new technology quickly for a project.", 'behavioral', 'intermediate', False, 150),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_tester_questions(self, job_title):
        """Add questions for Tester/QA role"""
        questions = [
            ("Tell me about your QA testing experience and methodologies.", 'general', 'easy', True, 120),
            ("How do you approach test case design and planning?", 'behavioral', 'intermediate', True, 150),
            ("What types of testing are you familiar with (unit, integration, system, etc.)?", 'technical', 'intermediate', True, 150),
            ("How do you prioritize which bugs to fix first?", 'situational', 'intermediate', False, 120),
            ("Describe your experience with automated testing tools.", 'technical', 'intermediate', False, 150),
            ("How do you test APIs and web services?", 'technical', 'intermediate', False, 150),
            ("What's your approach to regression testing?", 'technical', 'intermediate', False, 120),
            ("How do you communicate bugs to developers effectively?", 'behavioral', 'intermediate', False, 120),
            ("Describe your experience with performance and load testing.", 'technical', 'intermediate', False, 150),
            ("How do you ensure test coverage is adequate?", 'technical', 'intermediate', False, 120),
            ("What's your experience with mobile app testing?", 'technical', 'intermediate', False, 120),
            ("How do you handle testing in an Agile/Scrum environment?", 'behavioral', 'intermediate', False, 150),
            ("Describe a critical bug you found and how you handled it.", 'behavioral', 'intermediate', False, 180),
            ("How do you approach usability testing?", 'behavioral', 'intermediate', False, 120),
            ("What's your experience with security testing?", 'technical', 'hard', False, 150),
            ("How do you measure the effectiveness of your testing?", 'technical', 'intermediate', False, 120),
            ("Describe your experience with test management tools.", 'technical', 'intermediate', False, 120),
            ("How do you collaborate with developers in a DevOps environment?", 'behavioral', 'intermediate', False, 150),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_product_manager_questions(self, job_title):
        """Add questions for Product Manager role"""
        questions = [
            ("Tell me about your product management experience and philosophy.", 'general', 'easy', True, 120),
            ("How do you prioritize features in your product roadmap?", 'behavioral', 'intermediate', True, 150),
            ("Describe your approach to user research and gathering requirements.", 'behavioral', 'intermediate', True, 150),
            ("How do you balance technical feasibility with business requirements?", 'situational', 'intermediate', False, 150),
            ("What's your experience with A/B testing and product experimentation?", 'technical', 'intermediate', False, 150),
            ("How do you handle conflicting stakeholder requirements?", 'situational', 'intermediate', False, 150),
            ("Describe a product feature you launched and its impact.", 'behavioral', 'intermediate', False, 180),
            ("How do you measure product success and KPIs?", 'technical', 'intermediate', False, 120),
            ("What's your approach to competitive analysis?", 'behavioral', 'intermediate', False, 120),
            ("How do you work with engineering teams on product development?", 'behavioral', 'intermediate', False, 150),
            ("Describe your experience with product pricing and monetization strategies.", 'technical', 'intermediate', False, 150),
            ("How do you handle product failures or unsuccessful launches?", 'behavioral', 'hard', False, 180),
            ("What's your approach to product documentation and communication?", 'behavioral', 'intermediate', False, 120),
            ("How do you stay informed about market trends and customer needs?", 'behavioral', 'intermediate', False, 120),
            ("Describe your experience with agile product development methodologies.", 'technical', 'intermediate', False, 150),
            ("How do you make go/no-go decisions on product releases?", 'situational', 'intermediate', False, 150),
            ("What's your experience with internationalizing products for different markets?", 'behavioral', 'intermediate', False, 150),
            ("How do you gather and incorporate user feedback?", 'behavioral', 'intermediate', False, 120),
            ("Describe your experience with product analytics and data-driven decisions.", 'technical', 'intermediate', False, 150),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_hr_recruiter_questions(self, job_title):
        """Add questions for HR Recruiter role"""
        questions = [
            ("Tell me about your recruiting experience and specialty areas.", 'general', 'easy', True, 120),
            ("How do you source and attract top talent?", 'behavioral', 'intermediate', True, 150),
            ("Describe your approach to screening and interviewing candidates.", 'behavioral', 'intermediate', True, 150),
            ("How do you assess cultural fit during the hiring process?", 'situational', 'intermediate', False, 150),
            ("What's your experience with applicant tracking systems (ATS)?", 'technical', 'intermediate', False, 120),
            ("How do you build relationships with hiring managers?", 'behavioral', 'intermediate', False, 120),
            ("Describe your approach to negotiating salary and offers.", 'behavioral', 'intermediate', False, 150),
            ("How do you handle difficult conversations with candidates?", 'situational', 'intermediate', False, 150),
            ("What's your experience with diversity and inclusion initiatives?", 'behavioral', 'intermediate', False, 150),
            ("How do you measure the effectiveness of your recruiting efforts?", 'technical', 'intermediate', False, 120),
            ("Describe your experience with employer branding and recruitment marketing.", 'behavioral', 'intermediate', False, 150),
            ("How do you manage a high volume of open positions?", 'situational', 'intermediate', False, 150),
            ("What's your approach to passive candidate sourcing?", 'behavioral', 'intermediate', False, 120),
            ("How do you stay updated on labor market trends and compensation?", 'behavioral', 'intermediate', False, 120),
            ("Describe a time you filled a difficult-to-fill position.", 'behavioral', 'intermediate', False, 180),
            ("How do you ensure a positive candidate experience?", 'behavioral', 'intermediate', False, 120),
            ("What's your experience with recruitment metrics and analytics?", 'technical', 'intermediate', False, 120),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_business_analyst_questions(self, job_title):
        """Add questions for Business Analyst role"""
        questions = [
            ("Tell me about your business analysis experience and methodology.", 'general', 'easy', True, 120),
            ("How do you gather and document business requirements?", 'behavioral', 'intermediate', True, 150),
            ("Describe your experience with process modeling and workflow analysis.", 'technical', 'intermediate', True, 150),
            ("How do you handle conflicting requirements from stakeholders?", 'situational', 'intermediate', False, 150),
            ("What's your experience with SQL and data analysis for business insights?", 'technical', 'intermediate', False, 150),
            ("How do you facilitate workshops and requirement gathering sessions?", 'behavioral', 'intermediate', False, 150),
            ("Describe your approach to creating user stories and acceptance criteria.", 'technical', 'intermediate', False, 120),
            ("How do you validate that solutions meet business requirements?", 'technical', 'intermediate', False, 120),
            ("What's your experience with business intelligence tools (Tableau, Power BI)?", 'technical', 'intermediate', False, 120),
            ("How do you communicate technical concepts to non-technical stakeholders?", 'behavioral', 'intermediate', False, 120),
            ("Describe a process improvement project you led.", 'behavioral', 'intermediate', False, 180),
            ("How do you prioritize requirements when resources are limited?", 'situational', 'intermediate', False, 150),
            ("What's your experience with gap analysis and business case development?", 'technical', 'intermediate', False, 150),
            ("How do you handle scope changes during a project?", 'situational', 'intermediate', False, 150),
            ("Describe your experience with UML and system modeling.", 'technical', 'intermediate', False, 120),
            ("How do you ensure requirements are testable and measurable?", 'technical', 'intermediate', False, 120),
            ("What's your approach to stakeholder management?", 'behavioral', 'intermediate', False, 150),
            ("How do you use data to drive business decisions?", 'technical', 'intermediate', False, 150),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_customer_support_questions(self, job_title):
        """Add questions for Customer Support Specialist role"""
        questions = [
            ("Tell me about your customer service experience.", 'general', 'easy', True, 120),
            ("How do you handle angry or frustrated customers?", 'situational', 'intermediate', True, 150),
            ("Describe your approach to resolving complex customer issues.", 'behavioral', 'intermediate', True, 150),
            ("How do you prioritize multiple customer inquiries?", 'situational', 'intermediate', False, 120),
            ("What's your experience with customer support software and tools?", 'technical', 'intermediate', False, 120),
            ("How do you maintain patience during difficult interactions?", 'behavioral', 'intermediate', False, 120),
            ("Describe a time you turned a negative customer experience into a positive one.", 'behavioral', 'intermediate', False, 180),
            ("How do you communicate technical solutions to non-technical customers?", 'behavioral', 'intermediate', False, 120),
            ("What's your approach to documenting customer interactions?", 'technical', 'intermediate', False, 120),
            ("How do you handle situations where you don't know the answer?", 'situational', 'intermediate', False, 150),
            ("Describe your experience with upselling or cross-selling in support.", 'behavioral', 'intermediate', False, 120),
            ("How do you collaborate with other teams to resolve customer issues?", 'behavioral', 'intermediate', False, 120),
            ("What's your approach to de-escalating tense situations?", 'behavioral', 'intermediate', False, 120),
            ("How do you measure customer satisfaction in your role?", 'technical', 'intermediate', False, 120),
            ("Describe your experience with multichannel support (phone, email, chat).", 'behavioral', 'intermediate', False, 120),
            ("How do you stay updated on product knowledge and features?", 'behavioral', 'intermediate', False, 120),
            ("What's your experience with support ticket management systems?", 'technical', 'intermediate', False, 120),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_ui_ux_designer_questions(self, job_title):
        """Add questions for UI/UX Designer role"""
        questions = [
            ("Tell me about your UI/UX design experience and design philosophy.", 'general', 'easy', True, 120),
            ("How do you approach user research and persona development?", 'behavioral', 'intermediate', True, 150),
            ("Describe your design process from concept to final implementation.", 'behavioral', 'intermediate', True, 150),
            ("How do you balance aesthetics with usability in your designs?", 'situational', 'intermediate', False, 150),
            ("What design tools and software are you proficient in?", 'technical', 'intermediate', False, 120),
            ("How do you incorporate accessibility into your designs?", 'technical', 'intermediate', False, 150),
            ("Describe your experience with creating wireframes and prototypes.", 'technical', 'intermediate', False, 120),
            ("How do you handle design feedback and iteration?", 'behavioral', 'intermediate', False, 120),
            ("What's your approach to responsive and mobile-first design?", 'technical', 'intermediate', False, 120),
            ("How do you conduct usability testing and incorporate findings?", 'behavioral', 'intermediate', False, 150),
            ("Describe a design project where you significantly improved user experience.", 'behavioral', 'intermediate', False, 180),
            ("How do you work with developers to implement your designs?", 'behavioral', 'intermediate', False, 120),
            ("What's your experience with design systems and component libraries?", 'technical', 'intermediate', False, 120),
            ("How do you stay updated on design trends and best practices?", 'behavioral', 'intermediate', False, 120),
            ("Describe your approach to information architecture.", 'technical', 'intermediate', False, 120),
            ("How do you design for different user personas and use cases?", 'behavioral', 'intermediate', False, 150),
            ("What's your experience with A/B testing designs?", 'technical', 'intermediate', False, 120),
            ("How do you handle tight deadlines and design constraints?", 'situational', 'intermediate', False, 150),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)

    def _add_devops_engineer_questions(self, job_title):
        """Add questions for DevOps Engineer role"""
        questions = [
            ("Tell me about your DevOps experience and philosophy.", 'general', 'easy', True, 120),
            ("How do you approach CI/CD pipeline design and implementation?", 'technical', 'intermediate', True, 150),
            ("Describe your experience with infrastructure as code (Terraform, CloudFormation).", 'technical', 'intermediate', True, 150),
            ("How do you handle deployment failures and rollbacks?", 'situational', 'intermediate', False, 150),
            ("What's your experience with container orchestration (Kubernetes, Docker Swarm)?", 'technical', 'intermediate', False, 150),
            ("How do you ensure security in your DevOps practices?", 'technical', 'intermediate', False, 150),
            ("Describe your approach to monitoring and alerting in production.", 'technical', 'intermediate', False, 120),
            ("How do you automate infrastructure provisioning and scaling?", 'technical', 'intermediate', False, 150),
            ("What's your experience with configuration management tools (Ansible, Chef, Puppet)?", 'technical', 'intermediate', False, 120),
            ("How do you collaborate between development and operations teams?", 'behavioral', 'intermediate', False, 120),
            ("Describe your experience with cloud platforms (AWS, GCP, Azure).", 'technical', 'intermediate', False, 150),
            ("How do you handle secrets management in your infrastructure?", 'technical', 'intermediate', False, 120),
            ("What's your approach to capacity planning and resource optimization?", 'technical', 'intermediate', False, 120),
            ("How do you implement and enforce compliance and governance?", 'technical', 'intermediate', False, 150),
            ("Describe a major incident you responded to and what you learned.", 'behavioral', 'intermediate', False, 180),
            ("How do you measure and improve deployment frequency and reliability?", 'technical', 'intermediate', False, 120),
            ("What's your experience with service mesh and microservices networking?", 'technical', 'hard', False, 150),
            ("How do you handle disaster recovery and business continuity?", 'situational', 'intermediate', False, 150),
        ]
        for q_text, q_type, q_diff, q_mandatory, q_duration in questions:
            self._create_question(job_title, q_text, q_type, q_diff, q_mandatory, q_duration)
