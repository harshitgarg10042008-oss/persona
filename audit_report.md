# Audit Report — Heavy ML/CV Library Usage (Steps 1–2)

## Every import of cv2, mediapipe, torch, torchvision, transformers, whisper, librosa

| # | File | Function / Endpoint | What it does | Bucket | Already Groq API nearby? |
|---|------|---------------------|--------------|--------|--------------------------|
| 1 | `AnalysisModules/AnalysisAPI/views.py` (~line 5753) | `verify_face_on_start` | Decodes base64 webcam frame + reference photo with OpenCV; runs MediaPipe face detection on both; logs `no_face_detected` / `face_mismatch` events to `EnvironmentIntegrityEvent`; returns match yes/no | **A — Proctoring (video/webcam)** | No — purely local computation |
| 2 | `AnalysisModules/AnalysisAPI/views.py` (~line 5891) | `periodic_face_check` | Decodes base64 snapshot posted from frontend, MediaPipe face detection, logs `no_face_detected` / `multiple_faces_detected` | **A — Proctoring (video/webcam)** | No — purely local computation |
| 3 | `AnalysisModules/AnalysisAPI/tasks.py` (~line 375) | `process_cv_analysis_task` | Post-assessment background task: OpenCV samples video frames, MediaPipe Holistic (face iris gaze, pose, hands) computes `eye_contact_score`, `posture_score`, `gesture_score` (distraction proxy), plus a state-transition event timeline | **A — Proctoring (video)** | No — purely local computation |
| 4 | `AnalysisModules/AnalysisAPI/tasks.py` (~line 25) | `run_speech_analysis_task` → `AnalysisModules/speech_analyzer.py` | Extracts audio track from uploaded video via ffmpeg, local `whisper` ("base" model) transcription, `librosa` pitch/pitch variance/energy/spectral/silence features, `nltk`/`textblob` fluency-formality-content scoring | **B — Audio transcription** | No — local Whisper + librosa |
| 5 | `AnalysisModules/attire_analyzer.py` | `WebAttireAnalyzer.analyze_image` / `analyze_base64_image` | Loads `openai/clip-vit-base-patch32`, `Salesforce/blip-image-captioning-base`, `google/vit-base-patch16-224` (torch + torchvision + transformers) for professionalism analysis of snapshots posted every 10s during the assessment | **C — Local ML in other feature** | No — local models |
| 6 | `AnalysisModules/body_language_analyzer.py` | `WebBodyLanguageAnalyzer.analyze_image` / `analyze_base64_image` | MediaPipe pose + face mesh + hands analysis of snapshots posted every 5s during the assessment | **A/C — Proctoring-adjacent CV** | No — local computation |
| 7 | `AnalysisModules/AnalysisAPI/urls.py` | routes `capture-face-reference/`, `verify-face/`, `face-check/` | URL wiring for the three server-side CV endpoints above | — | — |

## Confirmed NOT using heavy libraries (left untouched)

- **Resume reviewer** (`resume_reviewer_upload` view, ~line 4375): prompt-based Groq LLM analysis; no torch/transformers.
- **Cover letter generator** (`cover_letter_generate`, ~line 4574): prompt-based Groq generation.
- **LinkedIn post generator** (`linkedin_post_generate`, ~line 4694): prompt-based Groq generation.
- `AnalysisModules/feedback_generator.py` — already uses `_call_groq` for answer-content evaluation (transcript scoring).
- `AnalysisModules/career_mentor.py` — Groq helpers only; no heavy imports.
- `AnalysisModules/recruiter_dashboard.py` — Groq helpers only; no heavy imports.
- `append_linkedin_views.py`, `check_questions.py`, `check_question_difficulty.py`, `classify_questions.py` (repo root scripts): no heavy imports.

## Requirements vs. actual usage summary

| requirements.txt entry | Actually needed? | After refactor |
|---|---|---|
| torch, torchvision, transformers | attire_analyzer only | Removed (attire analysis moves to client-side Groq vision-free prompt approach or is dropped in favor of client-side LLM scoring) |
| mediapipe | views (face check), tasks (CV), body_language_analyzer | Removed (all detection moves client-side via @mediapipe/tasks-vision WASM) |
| opencv-python | views (face check), tasks (video frames) | Removed |
| openai-whisper, librosa | speech_analyzer only | Removed (Groq hosted Whisper `whisper-large-v3`; fluency/formality via Groq LLM prompt) |
| numpy, Pillow | shared utility (numpy via Pillow/scikit-learn usage elsewhere) | KEPT |
| scikit-learn, nltk, textblob, ftfy, matplotlib, pypdf, regex, requests, seaborn, tqdm, xhtml2pdf, razorpay, SpeechRecognition, edge-tts | various non-heavy features | KEPT |
| groq, Django, gunicorn, psycopg2-binary, django-csp, django-q2, django-ratelimit, python-decouple | core | KEPT |

## Design notes for the refactor

- The frontend already ships `logIntegrityEvent()` which POSTs `{event_type, details}` JSON to the existing `log-integrity-event` endpoint (`log_integrity_event` view). That endpoint already handles `EnvironmentIntegrityEvent` creation, strike counting, and high-risk auto-lock — so client-side detection just needs to feed the same pipeline.
- `EnvironmentIntegrityEvent.EVENT_TYPE_CHOICES` already includes `no_face_detected`, `multiple_faces_detected`, `face_mismatch` — no new model strictly required; new choices (`phone_detected`) can be added to the model's choices.
- CSP currently blocks external scripts (`CSP_SCRIPT_SRC` is `self` + razorpay). The MediaPipe Tasks Vision CDN (`cdn.jsdelivr.net`) and its WASM files must be whitelisted, or alternatively the MediaPipe Tasks Vision bundle can be served from `static/`. Serving from CDN is the requested approach; CSP will be updated accordingly.
- `process_cv_analysis_task` is auto-queued on `complete_individual_assessment` and writes `eye_contact_score`/`posture_score`/`gesture_score`/`cv_analysis_events` onto `IndividualAssessment`. These fields stay on the model; the task will be rewritten to compute the same aggregates from client-generated events instead of processing video frames.
