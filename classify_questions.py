import os
import django
import json
import re
import sys
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("python-dotenv not installed, assuming env vars are set.")

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PersonaBackend.settings')
django.setup()

from AnalysisAPI.models import PlatformQuestion
from AnalysisAPI.models import InterviewQuestion
from django.conf import settings
try:
    from groq import Groq
except ImportError:
    Groq = None

def get_api_key():
    return getattr(settings, 'GROQ_API_KEY', None) or os.getenv('GROQ_API_KEY')

def classify_questions():
    api_key = get_api_key()
    if not api_key or Groq is None:
        print("Error: Groq API key or package is missing.")
        return

    client = Groq(api_key=api_key)
    model_name = getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')

def process_model(client, model_class, model_name, role_title_attr):
    questions = list(model_class.objects.all())
    model_label = model_class.__name__
    print(f"\n--- Found {len(questions)} {model_label}s to classify. ---")

    batch_size = 20
    for i in range(0, len(questions), batch_size):
        batch = questions[i:i+batch_size]
        
        prompt = f"You are an expert interview question classifier. Classify the difficulty of each of the following interview questions as 'beginner', 'intermediate', or 'advanced'.\n\n"
        for q in batch:
            role_title = getattr(q, role_title_attr).title if getattr(q, role_title_attr) else "General"
            prompt += f"ID: {q.id} | Role: {role_title} | Type: {q.question_type} | Question: {q.question_text}\n"
        
        prompt += "\nReturn ONLY a valid JSON object mapping the question ID (as string) to the difficulty level string ('beginner', 'intermediate', or 'advanced'). Example: {\"1\": \"beginner\", \"2\": \"advanced\"}"
        
        print(f"Processing {model_label} batch {i//batch_size + 1}...")
        try:
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                timeout=30,
            )
            text = chat_completion.choices[0].message.content or ''
            
            cleaned = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
            cleaned = re.sub(r'\s*```$', '', cleaned)
            
            try:
                results = json.loads(cleaned)
                for q in batch:
                    diff = results.get(str(q.id))
                    if diff in ['beginner', 'intermediate', 'advanced']:
                        q.difficulty_level = diff
                        q.save()
                        print(f"[{model_label}] ID {q.id} -> {diff}: {q.question_text[:50]}...")
            except json.JSONDecodeError:
                print(f"Failed to parse JSON for {model_label} batch {i//batch_size + 1}")
                print(text)
        except Exception as e:
            print(f"Error calling Groq for {model_label} batch {i//batch_size + 1}: {e}")

def classify_questions():
    api_key = get_api_key()
    if not api_key or Groq is None:
        print("Error: Groq API key or package is missing.")
        return

    client = Groq(api_key=api_key)
    model_name = getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')

    process_model(client, PlatformQuestion, model_name, "job_title")
    process_model(client, InterviewQuestion, model_name, "job_role")

if __name__ == '__main__':
    classify_questions()
