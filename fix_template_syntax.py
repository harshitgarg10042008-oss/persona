with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the broken timeLimitSeconds line
old_pattern = "let timeLimitSeconds = {% if time_limit_seconds %}{{ time_limit_seconds }} {% else %} null{% endif %};"
new_pattern = "let timeLimitSeconds = {% if time_limit_seconds %}{{ time_limit_seconds }}{% else %}null{% endif %};"

if old_pattern in content:
    content = content.replace(old_pattern, new_pattern)
    print('Fixed timeLimitSeconds line')
else:
    print('Pattern not found, trying regex...')
    import re
    # Match the pattern with extra spaces
    match = re.search(r"let timeLimitSeconds = \{% if time_limit_seconds %\}\{\s*time_limit_seconds\s*\}\s*\{% else %\}\s*null\s*\{% endif %\};", content)
    if match:
        print(f'Found: {match.group(0)}')
        content = re.sub(r"let timeLimitSeconds = \{% if time_limit_seconds %\}\{\s*time_limit_seconds\s*\}\s*\{% else %\}\s*null\s*\{% endif %\};", new_pattern, content)
        print('Fixed with regex')
    else:
        print('No match found')

with open('PersonaFrontend/templates/analysis/individual_assessment_question.html', 'w', encoding='utf-8') as f:
    f.write(content)
