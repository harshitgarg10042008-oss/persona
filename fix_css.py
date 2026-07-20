import re
import os
import glob

# Pattern: two consecutive dark:text-* classes (keeps the second/later one)
# Also handles three consecutive by running multiple times
PATTERN = re.compile(r'(dark:(?:text|bg|border|ring|placeholder)-[a-z]+-\d+)\s+(dark:(?:text|bg|border|ring|placeholder)-[a-z]+-\d+)')

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        original = f.read()

    # Keep applying until no more duplicates
    text = original
    while True:
        new_text = PATTERN.sub(lambda m: m.group(2), text)
        if new_text == text:
            break
        text = new_text

    if text != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(text)
        return True
    return False

if __name__ == '__main__':
    templates_dir = os.path.join(os.path.dirname(__file__), 'PersonaFrontend', 'templates')
    html_files = glob.glob(os.path.join(templates_dir, '**', '*.html'), recursive=True)

    fixed_count = 0
    for filepath in sorted(html_files):
        if fix_file(filepath):
            rel = os.path.relpath(filepath, os.path.dirname(__file__))
            print(f'Fixed: {rel}')
            fixed_count += 1

    print(f'\nDone. Fixed {fixed_count} file(s).')
