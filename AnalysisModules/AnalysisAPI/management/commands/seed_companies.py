from django.core.management.base import BaseCommand
from AnalysisAPI.models import CompanyProfile

class Command(BaseCommand):
    help = 'Seeds initial companies for Company-Specific Interviews Phase 1 & 2'

    def handle(self, *args, **options):
        companies = [
            {
                'name': 'Google',
                'industry': 'Big Tech',
                'interview_style_notes': (
                    'Focus heavily on analytical and structured problem-solving. '
                    'Expect questions that test the ability to handle scale, ambiguity, '
                    'and cross-functional collaboration. Answers should demonstrate '
                    'logical reasoning, data-driven decisions, and "Googliness" (thriving in ambiguity, '
                    'valuing feedback, challenging the status quo).'
                )
            },
            {
                'name': 'Amazon',
                'industry': 'Big Tech',
                'interview_style_notes': (
                    'Focus on the 16 Leadership Principles (e.g., Customer Obsession, '
                    'Bias for Action, Deliver Results, Ownership, Dive Deep). '
                    'Expect behavioral questions heavily emphasizing past experiences, data-driven '
                    'decision making, and overcoming obstacles. Answers MUST follow the STAR method strictly.'
                )
            },
            {
                'name': 'TCS',
                'industry': 'IT Services',
                'interview_style_notes': (
                    'Focus on process adherence, adaptability across different technologies, '
                    'client-centric delivery, and teamwork. Expect questions about handling '
                    'client requirements, working in large distributed teams, meeting strict deadlines, '
                    'and basic problem-solving without over-engineering.'
                )
            },
            {
                'name': 'Flipkart',
                'industry': 'E-commerce',
                'interview_style_notes': (
                    'Focus on e-commerce scale, agile problem-solving in fast-paced environments, '
                    'and deep technical ownership. Expect questions about building systems for '
                    'high traffic events (like Big Billion Days), handling operational bottlenecks, '
                    'and customer-first thinking in the Indian market context.'
                )
            },
            {
                'name': 'Microsoft',
                'industry': 'Big Tech',
                'interview_style_notes': (
                    'Focus on growth-mindset framing, collaborative problem-solving, and deep technical foundations. '
                    'Expect questions testing systems thinking, empathy in engineering, and the ability to navigate '
                    'complex enterprise scale. Answers should show a willingness to learn and cross-group collaboration.'
                )
            },
            {
                'name': 'Meta',
                'industry': 'Big Tech',
                'interview_style_notes': (
                    'Focus on a "move-fast" execution culture, impact-driven engineering, and extreme technical rigor. '
                    'Expect questions testing ability to scale systems to billions of users, pragmatic trade-offs, '
                    'and navigating ambiguity with data-backed decisions.'
                )
            },
            {
                'name': 'Apple',
                'industry': 'Big Tech',
                'interview_style_notes': (
                    'Focus on design obsession, product quality, cross-functional precision, and attention to detail. '
                    'Expect questions emphasizing privacy-first engineering, polished user experiences, and deep '
                    'domain expertise rather than generalized problem solving.'
                )
            },
            {
                'name': 'Netflix',
                'industry': 'Big Tech',
                'interview_style_notes': (
                    'Focus on high-performance culture, direct/candid communication, and extreme ownership. '
                    'Expect questions testing "freedom and responsibility", independent decision making, '
                    'and deep systems engineering with a focus on reliability.'
                )
            },
            {
                'name': 'Infosys',
                'industry': 'IT Services',
                'interview_style_notes': (
                    'Focus on continuous learning, structured problem solving, and navigating large enterprise processes. '
                    'Expect questions about client-facing communication, adapting to global delivery models, and '
                    'understanding business requirements.'
                )
            },
            {
                'name': 'Wipro',
                'industry': 'IT Services',
                'interview_style_notes': (
                    'Focus on diverse technology stacks, operational excellence, and a consulting-led approach. '
                    'Expect questions about maintaining SLAs, incident management, and adaptability across '
                    'different client domains and methodologies.'
                )
            },
            {
                'name': 'HCL',
                'industry': 'IT Services',
                'interview_style_notes': (
                    'Focus on "ideapreneurship", grassroots innovation, and strong technical foundations. '
                    'Expect questions testing engineering-centric problem solving, value creation for clients, '
                    'and deep infrastructure or systems knowledge.'
                )
            },
            {
                'name': 'Accenture',
                'industry': 'IT Services',
                'interview_style_notes': (
                    'Focus on business outcomes, technology consulting, and leading digital transformation projects. '
                    'Expect questions about agile delivery frameworks, translating technical solutions into business '
                    'value, and working with C-suite stakeholders.'
                )
            },
            {
                'name': 'Cognizant',
                'industry': 'IT Services',
                'interview_style_notes': (
                    'Focus on modernizing core systems, data-driven insights, and deep domain expertise. '
                    'Expect questions on client-first delivery, managing legacy-to-cloud migrations, and '
                    'industry-specific (like healthcare or financial) challenges.'
                )
            },
            {
                'name': 'Swiggy',
                'industry': 'Consumer Tech / Logistics',
                'interview_style_notes': (
                    'Focus on fast-paced consumer tech, hyperlocal logistics, extreme ownership, and scrappy problem-solving. '
                    'Expect questions on optimizing for extreme peak loads, delivery efficiency algorithms, and handling '
                    'real-world operational bottlenecks.'
                )
            },
            {
                'name': 'Zomato',
                'industry': 'Consumer Tech / Logistics',
                'interview_style_notes': (
                    'Focus on data-driven personalization, quirky and creative problem-solving, and growth hacking. '
                    'Expect questions on operational scalability in food delivery, customer acquisition, and making '
                    'fast product iterations.'
                )
            },
            {
                'name': 'Paytm',
                'industry': 'Fintech',
                'interview_style_notes': (
                    'Focus on fintech-specific challenges: trust, security-first engineering, and compliance-awareness. '
                    'Expect questions on handling extreme scales of transactions, robust financial systems architecture, '
                    'and handling concurrency and data consistency.'
                )
            }
        ]

        created_count = 0
        updated_count = 0

        for company_data in companies:
            obj, created = CompanyProfile.objects.update_or_create(
                name=company_data['name'],
                defaults={
                    'industry': company_data['industry'],
                    'interview_style_notes': company_data['interview_style_notes']
                }
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully seeded companies: {created_count} created, {updated_count} updated.'
            )
        )
