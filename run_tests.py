import os
import django
from django.conf import settings
from django.test.utils import get_runner

os.environ['DJANGO_SETTINGS_MODULE'] = 'PersonaBackend.settings'
django.setup()
TestRunner = get_runner(settings)
test_runner = TestRunner(verbosity=2, stream=open('test_output.txt', 'w'))
failures = test_runner.run_tests(['AnalysisModules'])
print(f"Failures: {failures}")
