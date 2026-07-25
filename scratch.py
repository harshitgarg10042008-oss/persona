import re
import sys

path = r'PersonaFrontend\templates\analysis\individual_assessment_complete.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all occurrences of {% if ... %}, {% elif ... %}, {% else %}, {% endif %}
tags = []
# We match {% followed by whitespace, then the tag name.
# Also handle tags spanning multiple lines.
for m in re.finditer(r'\{%\s*(if|endif|elif|else)\b', content):
    line_no = content.count('\n', 0, m.start()) + 1
    tags.append((m.group(1), line_no))

stack = []
unmatched_endifs = []
for tag, lno in tags:
    if tag == 'if':
        stack.append(lno)
    elif tag == 'endif':
        if stack:
            stack.pop()
        else:
            unmatched_endifs.append(lno)

print("Total if:", len([t for t, l in tags if t == 'if']))
print("Total endif:", len([t for t, l in tags if t == 'endif']))

if stack:
    print("Unclosed {% if %} at lines:", stack)
if unmatched_endifs:
    print("Unmatched {% endif %} at lines:", unmatched_endifs)

if not stack and not unmatched_endifs:
    print("All if/endif tags are perfectly matched!")
