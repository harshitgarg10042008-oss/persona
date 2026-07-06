import sys
import os
import traceback

outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dryrun_output.txt')
outfile = open(outpath, 'w', encoding='utf-8')

def log(msg=""):
    outfile.write(str(msg) + "\n")
    outfile.flush()

log("Script starting...")

try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    log(f"sys.path[0] = {sys.path[0]}")
    
    os.environ['DJANGO_SETTINGS_MODULE'] = 'PersonaBackend.settings'
    log("DJANGO_SETTINGS_MODULE set")

    import django
    log(f"Django version: {django.__version__}")
    django.setup()
    log("Django setup complete")

    from AnalysisModules.feedback_generator import (
        generate_tailored_questions,
        _get_api_key,
        _get_model_name,
    )
    log("Imports successful")

    RESUME_TEXT = (
        "John Smith - Senior Backend Engineer. "
        "Built REST APIs with Django and FastAPI serving 2M+ daily requests. "
        "Led 4-person team to migrate monolith to microservices on AWS ECS. "
        "Reduced API latency by 40% using Redis caching and query optimization. "
        "Implemented CI/CD pipelines with GitHub Actions and Docker. "
        "Developed React frontend, wrote pytest unit and integration tests with 90% coverage. "
        "B.Sc. Computer Science - State University (2019). "
        "Skills: Python, Django, FastAPI, React, PostgreSQL, Redis, Docker, AWS, Git. "
        "Projects: PersonaBot (2023) - video interview analysis using OpenCV and Whisper. "
        "DataPipeline (2022) - ETL processing 500GB/day using Apache Airflow."
    )

    JOB_ROLE = "Software Engineer"

    log("=" * 60)
    log("RESUME TAILORED QUESTION DRY-RUN TEST")
    log("=" * 60)
    log(f"API key present: {bool(_get_api_key())}")
    log(f"Model: {_get_model_name()}")
    log(f"Resume length: {len(RESUME_TEXT)} chars")
    log(f"Job role: {JOB_ROLE}")
    log()

    log("Calling generate_tailored_questions()...")
    questions = generate_tailored_questions(
        resume_text=RESUME_TEXT,
        job_role=JOB_ROLE,
        num_questions=5,
    )

    log(f"Questions generated: {len(questions)}")
    log()
    if questions:
        for i, q in enumerate(questions, 1):
            log(f"Q{i}: {q}")
    else:
        log("ERROR: No questions returned - check Groq API key / connectivity")

    log()
    log("=" * 60)
    log("FALLBACK TEST (empty resume -> should return [])")
    log("=" * 60)
    empty_questions = generate_tailored_questions(
        resume_text="",
        job_role=JOB_ROLE,
        num_questions=5,
    )
    log(f"Empty resume result: {empty_questions!r}")
    log("Expected: [] (triggers fallback to PlatformQuestion bank in views.py)")

except Exception as e:
    log(f"SCRIPT ERROR: {type(e).__name__}: {e}")
    log(traceback.format_exc())
finally:
    outfile.close()
