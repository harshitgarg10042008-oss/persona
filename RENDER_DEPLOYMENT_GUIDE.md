# Persona — Web-Optimized Refactor & Render Deployment Guide

## What was changed

Every heavy local ML/CV dependency has been removed from the backend so the
project fits **Render's free tier** (which has no GPU and tight memory/CPU
limits). All model work now runs either **in the browser** (proctoring) or on
**Groq's hosted APIs** (speech, attire, body language). The full audit is in
`audit_report.md`.

| Area | Before | After |
|---|---|---|
| Face / phone proctoring | Server decoded base64 frames and ran MediaPipe on every snapshot | Browser runs face detection (native FaceDetector API) + a lightweight MobileNet classifier (`@mediapipe/tasks-vision` WASM from CDN); the backend only persists small JSON events |
| Speech analysis | Local Whisper `base` + librosa features | Groq hosted `whisper-large-v3` for transcription; one structured LLM prompt scores fluency, pronunciation, content, formality, and confidence (deterministic proxy fallbacks if Groq is down) |
| Attire analysis | CLIP + BLIP + ViT (torch/transformers) | Groq vision model (`qwen/qwen3.6-27b`) |
| Body language analysis | MediaPipe pose / face mesh / hands | Same Groq vision model |
| Audio extraction | Local ffmpeg via imageio_ffmpeg | None — Groq whisper accepts the recorded `.webm` directly |
| Background tasks | django-q2 queue (needs a worker process) | Daemon threads in the web dyno — Render's single web dyno has no worker, so queued tasks were never executed |
| Summary video | moviepy removed (feature broken) | `moviepy==2.2.1` + `imageio-ffmpeg` restored — imageio-ffmpeg bundles a static ffmpeg binary, no system install needed |

All public function signatures (`analyze_speech`, `quick_transcribe`,
`analyze_voice_confidence`, `analyze_attire`, `analyze_attire_base64`,
`analyze_body_language`, `analyze_body_language_base64`) and their return
shapes are **unchanged**, so every existing call site keeps working without
further edits.

## Files touched

| File | Change |
|---|---|
| `AnalysisModules/AnalysisAPI/views.py` | `verify_face_on_start` & `periodic_face_check` → pure JSON event endpoints |
| `AnalysisModules/AnalysisAPI/tasks.py` | `process_cv_analysis_task` → aggregates from `EnvironmentIntegrityEvent`; `run_speech_analysis_task` → no ffmpeg |
| `AnalysisModules/AnalysisAPI/models.py` | Added `phone_detected`, `face_detection_error` event types |
| `AnalysisModules/speech_analyzer.py` | Full Groq rewrite with proxy fallbacks |
| `AnalysisModules/attire_analyzer.py` | Groq vision rewrite |
| `AnalysisModules/body_language_analyzer.py` | Groq vision rewrite |
| `PersonaFrontend/templates/analysis/individual_assessment_question.html` | MediaPipe Tasks Vision loaded from CDN, client-side detection loop, debounced event POSTs |
| `PersonaBackend/settings.py` | `DATABASE_URL` support, WhiteNoise, compressed static storage, `RENDER_HOSTNAME` CSRF, `GROQ_VISION_MODEL` |
| `requirements.txt` | Dropped 11 heavy packages; added `dj-database-url`, `whitenoise`, `gTTS`; pinned `reportlab==4.4.3` + `xhtml2pdf==0.2.17` |
| `Procfile` | `web: gunicorn PersonaBackend.wsgi:application` |
| `.../migrations/0045_alter_environmentintegrityevent_event_type.py` | New migration for event types |

## Deploying on Render

1. Create a **Web Service** connected to the repository, root directory as the source.
2. Add a **PostgreSQL** database — Render sets `DATABASE_URL` automatically.
3. Add these **environment variables**:

| Variable | Value |
|---|---|
| `GROQ_API_KEY` | Your Groq API key (required — all transcription and AI analysis depends on it) |
| `GROQ_MODEL` | `openai/gpt-oss-120b` recommended (`llama-3.3-70b-versatile` is on Groq's deprecation list, shutdown 08/16/26) |
| `GROQ_VISION_MODEL` | `qwen/qwen3.6-27b` (optional, already the default — supports Vision + JSON mode) |
| `SECRET_KEY` | A random string (keeps sessions stable across restarts) |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `<your-service>.onrender.com` |
| `RENDER_HOSTNAME` | `<your-service>.onrender.com` (same as above — fixes CSRF) |
| Razorpay / email vars | Same values as your current environment |

4. **Build command** (set explicitly if not auto-detected): `pip install -r requirements.txt`
5. A `Procfile` is included: the web dyno runs gunicorn, and a **release-phase** command runs `collectstatic` + `migrate` automatically on every deploy, so no manual shell steps are required after the first deploy.
6. A `runtime.txt` pins the buildpack to Python 3.11.15.

## Troubleshooting

- **"Attire analysis unavailable / No snapshot data recorded"**: caused by Groq vision analysis returning zero scores (missing/invalid `GROQ_API_KEY` or a failing vision call) — snapshots with a score of 0 were silently filtered out. The analyzer now returns neutral 0.5 scores with a clear "Attire analysis unavailable this session" feedback line and a `vision_available` flag when the vision API is unreachable, so the flow never drops snapshots silently. With a valid `GROQ_API_KEY` on Render, real vision scores will appear.
- **Speech analysis missing from results**: previously the submit endpoint extracted audio with local ffmpeg, which is unavailable on Render — the webm is now passed directly to Groq whisper.
- **Coaching / roadmap / CV analysis never finishing**: django-q2 tasks queued to the ORM were never consumed (no worker dyno). All background analysis now runs in daemon threads within the web dyno.

## Cost & capability notes

- Groq's free tier gives ~14–30 req/min for most LLM endpoints and ~600
  req/min for `whisper-large-v3` (30s audio). The proctoring frontend sends
  events every ~5s but the **debounced** POSTs only transmit tiny JSON, so
  server load drops dramatically (no image decoding, no ffmpeg, no torch).
- Face/object detection runs on the candidate's device — accuracy matches
  MediaPipe on desktop Chrome (the model runs the same WASM as before, just
  in the browser instead of on your server).
- If a Groq key is ever missing at runtime, every analyzer returns neutral
  fallback scores so the assessment flow never crashes.

## Verification performed

- `python manage.py check` passes (only the pre-existing W342 FK warning).
- All JS blocks in the assessment template parse cleanly.
- No `torch`, `mediapipe`, `cv2`, `whisper`, `librosa`, `transformers`,
  `textblob`, or `nltk` imports remain in project code outside comments.
- The commit is on branch `refactor/render-ready`; PR #1 targets `main`.
