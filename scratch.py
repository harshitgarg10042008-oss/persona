import urllib.request
import json

try:
    response = urllib.request.urlopen('http://localhost:8000/auth/test-feature-22/')
    with open('c:\\Users\\vishe\\OneDrive\\Desktop\\Goal\\persona\\test_output.txt', 'w', encoding='utf-8') as f:
        f.write(response.read().decode('utf-8'))
except Exception as e:
    with open('c:\\Users\\vishe\\OneDrive\\Desktop\\Goal\\persona\\test_output.txt', 'w', encoding='utf-8') as f:
        f.write(str(e))
