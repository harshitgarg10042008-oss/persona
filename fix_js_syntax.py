with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the broken timeLimitSeconds line
old_pattern1 = 'let timeLimitSeconds = {% if time_limit_seconds %}{ { time_limit_seconds } } {% else %} null{% endif %};'
new_pattern1 = 'let timeLimitSeconds = {% if time_limit_seconds %}{{ time_limit_seconds }}{% else %}null{% endif %};'

if old_pattern1 in content:
    content = content.replace(old_pattern1, new_pattern1)
    print('Fixed timeLimitSeconds broken spacing')
else:
    print('Pattern 1 not found')

# Fix the multi-line persona_name tag
old_pattern2 = '''<span id="interviewer-name" class="text-sm font-semibold text-indigo-700 dark:text-indigo-300">{{
              persona_name|default:'Interviewer' }}</span>'''
new_pattern2 = '''<span id="interviewer-name" class="text-sm font-semibold text-indigo-700 dark:text-indigo-300">{{ persona_name|default:'Interviewer' }}</span>'''

if old_pattern2 in content:
    content = content.replace(old_pattern2, new_pattern2)
    print('Fixed persona_name multi-line tag')
else:
    print('Pattern 2 not found')

# Fix the multi-line isMandatory tag
old_pattern3 = '''const isMandatory = {{ question.is_mandatory| yesno: "true,false"
  }};'''
new_pattern3 = 'const isMandatory = {{ question.is_mandatory|yesno:"true,false" }};'

if old_pattern3 in content:
    content = content.replace(old_pattern3, new_pattern3)
    print('Fixed isMandatory multi-line tag')
else:
    print('Pattern 3 not found')

with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
