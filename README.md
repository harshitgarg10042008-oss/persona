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

## 🧠 ML Pipeline & Features

This project integrates a comprehensive Machine Learning and AI pipeline:

- **Attire & Professionalism**: Uses **CLIP**, **BLIP**, and **ViT** models to assess the candidate's clothing and environment from video frames.
- **Body Language**: Uses **MediaPipe** to track posture, gestures, and facial landmarks for engagement and confidence metrics.
- **Speech & Fluency**: Uses **OpenAI Whisper** and `librosa` for robust audio transcription and vocal delivery analysis.
- **Content Correctness**: Utilizes **Google Gemini (3.1 Pro)** to deeply evaluate the transcript against the interview question and provide an actionable Feedback Summary.
- **Asynchronous Task Queue**: Leverages **Django-Q2** (via ORM broker) to process heavy ML operations in the background without blocking the main server threads.
- **PDF Reports & Tracking**: Generates downloadable PDF reports with detailed performance breakdowns and tracks progress via interactive charts (Chart.js) over time.

---

## 🚀 How to Run Locally

Currently, there are no heavy production deployment configurations (like Docker or Kubernetes). The project runs using the local Django server but requires an asynchronous worker for ML tasks.

**Step 1: Install System Dependencies**
- You must have **FFmpeg** installed on your system and available in your PATH for audio processing.

**Step 2: Create and activate a virtual environment**
```bash
python -m venv venv

# On Windows:
.\venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate
```

**Step 3: Setup Environment Variables**
- Copy `.env.example` to `.env` (or create a `.env` file).
- Ensure `SECRET_KEY`, `DEBUG`, and `GEMINI_API_KEY` are configured properly.

**Step 4: Install Dependencies**
```bash
# This will install Django as well as all heavy ML libraries (PyTorch, Transformers, MediaPipe, Whisper)
# NOTE: This may take 10-20 minutes depending on your internet speed.
pip install -r requirements.txt
```

**Step 5: Run the Task Worker (Django-Q2)**
In a new terminal (with the venv activated), run the task cluster for background audio processing:
```bash
python manage.py qcluster
```

**Step 6: Run the Development Server**
In your main terminal, run:
```bash
python manage.py runserver
```

**Step 7: Access the Website & Admin Panel**
- **Website:** Go to `http://127.0.0.1:8000`
- **Admin Panel:** Go to `http://127.0.0.1:8000/admin/`
  - *(To create an admin, run `python manage.py createsuperuser` in your terminal)*

---

## ⚠️ Known Flaws and Limitations

1. **No Production Deployment Configuration:**
   - The application lacks production-ready deployment setups (e.g., Dockerfile, Gunicorn, Nginx, or cloud hosting scripts).
   - The database still uses the default local `db.sqlite3` file, which is not suitable for high-concurrency production and should be migrated to PostgreSQL.
2. **Heavy ML Dependencies:**
   - The project installs large ML libraries natively (PyTorch is ~2.5 GB). In a true production environment, the ML analysis should be decoupled into a separate microservice, or heavily utilize caching, because deploying these models inside a single monolithic Django app will cause huge memory usage.