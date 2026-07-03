import traceback
try:
    import os, sys, json
    sys.stdout.reconfigure(encoding='utf-8')
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
    django.setup()
    from AnalysisModules.feedback_generator import generate_improvement_roadmap
    scores = {'overall_score': 6.2, 'body_language_score': 7.0, 'attire_score': 8.5, 'speaking_score': 5.5}
    speech_details = {'details': {'fluency': {'filler_count': 12, 'filler_ratio': 0.08, 'words_per_minute': 95, 'silence_ratio': 0.25}}}
    roadmap = generate_improvement_roadmap(scores, speech_details)
    with open('mock_roadmap.json', 'w', encoding='utf-8') as f:
        json.dump(roadmap, f, indent=2)
except Exception as e:
    with open('test_err.txt', 'w', encoding='utf-8') as f:
        f.write(traceback.format_exc())
