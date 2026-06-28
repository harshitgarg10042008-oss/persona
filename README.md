# Persona: AI-Driven Candidate Assessment System

Persona is a Django-based web application that conducts AI-driven candidate interviews and assessments. It evaluates a candidate's video and audio responses in real-time or asynchronously using advanced Machine Learning models to score their **attire, body language, and speech fluency/content**.

The system serves two main user personas:
1. **Individual Users:** Can practice interviews for platform-defined job titles.
2. **Business Users (Recruiters):** Can create custom job roles, define specific questions, and generate unique assessment links to share with candidates.

---

## 🏗️ Project Structure

The codebase is modularized into several Django apps:

```text
persona/
├── AnalysisModules/        # Core ML logic and AI pipelines
│   ├── attire_analyzer.py          # Uses CLIP, BLIP, ViT for attire/professionalism
│   ├── body_language_analyzer.py   # Uses MediaPipe for posture, eye contact, gestures
│   ├── speech_analyzer.py          # Uses Whisper, librosa, nltk for fluency and content
│   └── AnalysisAPI/                # Django app linking the ML modules to the frontend
├── PersonaBackend/         # Django project settings and root routing
├── PersonaFrontend/        # HTML templates, CSS, and JS (Recording UI and Dashboards)
├── UserAPI/                # Authentication, Individual and Business user models
├── DataAPI/                # Secondary app placeholder
└── requirements.txt        # All required dependencies
```

---

## 🚀 How to Run Locally

Currently, there are no deployment configurations (no Dockerfile, Procfile, or production DB). The project is meant to be run locally using the Django development server.

**Step 1: Create and activate a virtual environment**
```bash
python -m venv venv

# On Windows:
.\venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate
```

**Step 2: Install Dependencies**
```bash
# This will install Django as well as all heavy ML libraries (PyTorch, Transformers, MediaPipe, Whisper)
# NOTE: This may take 10-20 minutes depending on your internet speed.
pip install -r requirements.txt
```

**Step 3: Run the Development Server**
```bash
python manage.py runserver
```

**Step 4: Access the Website & Admin Panel**
- **Website:** Go to `http://127.0.0.1:8000`
- **Admin Panel:** Go to `http://127.0.0.1:8000/admin/`
  - *(To create an admin, run `python manage.py createsuperuser` in your terminal)*

---

## ⚠️ Known Flaws and Limitations

1. **MediaPipe Compatibility on Python 3.12:**
   - There is a known bug with `mediapipe` on Python 3.12 where it fails to expose its `solutions` module (usually due to an underlying C++ DLL issue on Windows). 
   - **Current Workaround:** The code in `body_language_analyzer.py` catches this error gracefully and simply disables body language analysis without crashing the server.
2. **No Deployment Configuration:**
   - The application has no production-ready deployment configurations (e.g., Dockerfile, Gunicorn, Nginx, or cloud hosting scripts).
   - The database uses the default local `db.sqlite3` file, which is not suitable for production. It should be migrated to PostgreSQL.
   - `DEBUG = True` is still set in `settings.py`.
3. **Heavy ML Dependencies:**
   - The project installs large ML libraries natively (PyTorch is ~2.5 GB). In a production environment, you might want to run the ML analysis on a separate microservice, or heavily utilize caching, because deploying these models inside a single monolithic Django app will cause huge memory usage and slow server boot times.
4. **Synchronous Audio Processing:**
   - While some ML tasks are threaded, running Whisper and Librosa processing directly in Django views can block the server or result in timeout errors if the audio files are too long. A task queue like **Celery + Redis** is highly recommended for production.