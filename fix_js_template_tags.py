with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the broken timeLimitSeconds line (leftover from integrity tracking)
old_pattern1 = 'let timeLimitSeconds = {% if time_limit_seconds %}{ { time_limit_seconds } } {% else %} null{% endif %};'
new_pattern1 = 'let timeLimitSeconds = {% if time_limit_seconds %}{{ time_limit_seconds }}{% else %}null{% endif %};'

if old_pattern1 in content:
    content = content.replace(old_pattern1, new_pattern1)
    print('Fixed timeLimitSeconds broken spacing')
else:
    print('Pattern 1 not found')

# Fix the multi-line isMandatory tag
old_pattern2 = '''const isMandatory = {{ question.is_mandatory| yesno: "true,false"
  }};'''
new_pattern2 = 'const isMandatory = {{ question.is_mandatory|yesno:"true,false" }};'

if old_pattern2 in content:
    content = content.replace(old_pattern2, new_pattern2)
    print('Fixed isMandatory multi-line tag')
else:
    print('Pattern 2 not found')

with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
