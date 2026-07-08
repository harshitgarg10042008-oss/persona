import os
import re

template_dir = r'c:\Users\vishe\OneDrive\Desktop\Samyak\persona\PersonaFrontend\templates'
colors = r'(blue|green|purple|red|yellow|amber|indigo)'

# For bg-color-50
pattern50 = re.compile(r'\bbg-' + colors + r'-50\b(?!\s*dark:bg)')
# For bg-color-100
pattern100 = re.compile(r'\bbg-' + colors + r'-100\b(?!\s*dark:bg)')

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = pattern50.sub(r'bg-\1-50 dark:bg-\1-900/20', content)
    new_content = pattern100.sub(r'bg-\1-100 dark:bg-\1-900/40', new_content)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'Updated: {filepath}')

for root, dirs, files in os.walk(template_dir):
    for file in files:
        if file.endswith('.html'):
            process_file(os.path.join(root, file))
print('Done!')
