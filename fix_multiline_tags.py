with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the multi-line persona_name tag
old_pattern = '''<span id="interviewer-name" class="text-sm font-semibold text-indigo-700 dark:text-indigo-300">{{
              persona_name|default:'Interviewer' }}</span>'''
new_pattern = '''<span id="interviewer-name" class="text-sm font-semibold text-indigo-700 dark:text-indigo-300">{{ persona_name|default:'Interviewer' }}</span>'''

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    print('Fixed persona_name multi-line tag')
else:
    print('Pattern not found in individual_assessment_question.html')

with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'w', encoding='utf-8') as f:
    f.write(content)

# Fix dashboard file
with open('PersonaFrontend/templates/dashboard/individual_dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix platform_job_title tag
old_pattern1 = '''<h3 class="font-semibold text-gray-700 dark:text-gray-400">{{
                            assessment.platform_job_title.title|default:"Assessment" }}</h3>'''
new_pattern1 = '''<h3 class="font-semibold text-gray-700 dark:text-gray-400">{{ assessment.platform_job_title.title|default:"Assessment" }}</h3>'''

if old_pattern1 in content:
    content = content.replace(old_pattern1, new_pattern1)
    print('Fixed platform_job_title multi-line tag')
else:
    print('Pattern 1 not found in individual_dashboard.html')

# Fix membership tag
old_pattern2 = '''<h4 class="font-semibold text-gray-800 dark:text-gray-100">{{
                            membership.business.company_name|default:membership.business.name }}</h4>'''
new_pattern2 = '''<h4 class="font-semibold text-gray-800 dark:text-gray-100">{{ membership.business.company_name|default:membership.business.name }}</h4>'''

if old_pattern2 in content:
    content = content.replace(old_pattern2, new_pattern2)
    print('Fixed membership multi-line tag')
else:
    print('Pattern 2 not found in individual_dashboard.html')

with open('PersonaFrontend/templates/dashboard/individual_dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
