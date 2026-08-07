with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the broken timeLimitSeconds line
old_pattern = 'let timeLimitSeconds = {% if time_limit_seconds %}{ { time_limit_seconds } } {% else %} null{% endif %};'
new_pattern = "let timeLimitSeconds = {% if time_limit_seconds %}{{ time_limit_seconds }}{% else %}null{% endif %};"

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    print('Fixed timeLimitSeconds broken spacing')
else:
    print('Pattern not found - checking current content...')
    # Print the relevant line for debugging
    for i, line in enumerate(content.split('\n'), 1):
        if 'timeLimitSeconds' in line and 'let' in line:
            print(f'Line {i}: {line.strip()}')

with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')
