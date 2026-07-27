import base64
import hashlib
from .models import IndividualAssessmentResponse
from AnalysisModules.feedback_generator import evaluate_answer_content

try:
    from AnalysisModules import analyze_speech, analyze_voice_confidence
except ImportError:
    def analyze_speech(*args, **kwargs):
        return {"error": "Speech analysis not available"}
    def analyze_voice_confidence(*args, **kwargs):
        return {"error": "Voice confidence analysis not available"}


def _decode_audio_base64(audio_data: str) -> bytes:
    """Decode base64 audio, stripping a data-URL prefix when present."""
    if not audio_data:
        return b''
    raw = audio_data.strip()
    if raw.startswith('data:') and ',' in raw:
        raw = raw.split(',', 1)[1]
    return base64.b64decode(raw)


def run_speech_analysis_task(response_id, question_text):
    """
    Background task to analyze speech and update the assessment response.
    Extracts audio from the saved video_file.
    """
    try:
        response = IndividualAssessmentResponse.objects.get(id=response_id)
    except IndividualAssessmentResponse.DoesNotExist:
        print(f"Task failed: Response {response_id} not found.")
        return

    try:
        if not response.video_file:
            print(f"Speech analysis skipped for response {response_id}: no video file")
            return

        import os
        import subprocess
        import tempfile

        video_path = response.video_file.path
        if not os.path.exists(video_path):
            print(f"Speech analysis skipped for response {response_id}: video file not found at {video_path}")
            return

        # Use imageio_ffmpeg (a moviepy dependency) to locate the bundled ffmpeg binary.
        # This avoids depending on ffmpeg being on PATH and, crucially, bypasses
        # moviepy's VideoFileClip which requires duration metadata in the webm header.
        # Chrome's MediaRecorder writes .webm without that header metadata, causing
        #   OSError: MoviePy error: failed to read the duration of ...
        # Raw ffmpeg handles headerless-duration webm files without complaint.
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            ffmpeg_bin = get_ffmpeg_exe()
        except Exception:
            ffmpeg_bin = "ffmpeg"  # fall back to PATH if imageio_ffmpeg unavailable

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
            temp_audio_path = temp_audio.name

        try:
            result = subprocess.run(
                [
                    ffmpeg_bin,
                    "-y",               # overwrite output without prompting
                    "-i", video_path,
                    "-vn",              # no video
                    "-acodec", "pcm_s16le",
                    "-ar", "16000",     # Whisper expects 16kHz
                    "-ac", "1",         # Whisper expects mono
                    temp_audio_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            print(f"Speech analysis skipped for response {response_id}: ffmpeg binary not found")
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            return

        if result.returncode != 0:
            stderr_text = result.stderr.decode(errors="replace")
            print(f"Speech analysis skipped for response {response_id}: ffmpeg exited {result.returncode}\n{stderr_text}")
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            return

        if not os.path.exists(temp_audio_path) or os.path.getsize(temp_audio_path) == 0:
            print(f"Speech analysis skipped for response {response_id}: ffmpeg produced no audio output (video may have no audio track)")
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            return

        with open(temp_audio_path, 'rb') as f:
            audio_bytes = f.read()

        os.remove(temp_audio_path)

        audio_hash = hashlib.md5(audio_bytes).hexdigest()

        analysis_data = response.analysis_data or {}
        analysis_data['debug_audio'] = {
            'bytes_len': len(audio_bytes),
            'hash': audio_hash,
        }

        if len(audio_bytes) < 1024:
            analysis_data['speech_analysis'] = {
                'error': f'Audio too small ({len(audio_bytes)} bytes) — recording likely empty',
                'transcription': '',
                'word_count': 0,
            }
            analysis_data['speech_analysis_status'] = 'completed'
            response.analysis_data = analysis_data
            response.save()
            print(f"Speech analysis skipped for response {response_id}: audio only {len(audio_bytes)} bytes")
            return

        speech_analysis = analyze_speech(audio_bytes, question_text)

        def convert_numpy_types(obj):
            if hasattr(obj, 'item'):
                return obj.item()
            elif hasattr(obj, 'tolist'):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {key: convert_numpy_types(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            return obj

        cleaned_analysis = convert_numpy_types(speech_analysis)

        speech_transcript = cleaned_analysis.get('transcription', '') or ''
        ideal_answer_points = getattr(response.question, 'ideal_answer_points', None)
        content_evaluation = evaluate_answer_content(
            question_text=response.question.question_text,
            transcript=speech_transcript,
            ideal_answer_points=ideal_answer_points,
        )

        # Perform voice confidence analysis
        voice_confidence_analysis = analyze_voice_confidence(audio_bytes, speech_transcript)
        cleaned_voice_confidence = convert_numpy_types(voice_confidence_analysis)

        analysis_data['speech_analysis'] = cleaned_analysis
        analysis_data['voice_confidence'] = cleaned_voice_confidence
        analysis_data['content_evaluation'] = content_evaluation
        analysis_data['speech_analysis_status'] = 'completed'
        
        response.analysis_data = analysis_data
        response.response_text = speech_transcript
        response.fluency_score = cleaned_analysis.get('fluency_score', 0)
        response.pronunciation_score = cleaned_analysis.get('pronunciation_score', 0)
        response.relevance_score = cleaned_analysis.get('content_score', 0)
        response.confidence_score = cleaned_analysis.get('confidence_score', 0)
        
        response.save()
        print(f"Speech analysis for response {response_id} completed successfully ({len(audio_bytes)} bytes).")

    except Exception as e:
        print(f"Speech analysis failed for response {response_id}: {e}")
        analysis_data = response.analysis_data or {}
        analysis_data['speech_analysis'] = {"error": str(e)}
        analysis_data['speech_analysis_status'] = 'failed'
        response.analysis_data = analysis_data
        response.save()


def generate_summary_video_task(video_id):
    """
    Background task to generate an interview summary video.
    Takes an InterviewSummaryVideo id, generates the video, and updates the record.
    """
    import logging
    logger = logging.getLogger(__name__)
    from .models import InterviewSummaryVideo
    from .video_generator import generate_summary_video

    logger.info(f"[SUMMARY VIDEO TASK] Starting task for video_record {video_id}")
    video_record = None
    try:
        video_record = InterviewSummaryVideo.objects.get(id=video_id)
        # Guard against duplicate execution: if already processing or completed, exit early
        if video_record.status in ('processing', 'completed'):
            logger.warning(f"[SUMMARY VIDEO TASK] Video record {video_id} already in status '{video_record.status}'. Skipping duplicate task.")
            return
        logger.info(f"[SUMMARY VIDEO TASK] Found video_record {video_id}, setting status to 'processing'")
        video_record.status = 'processing'
        video_record.save(update_fields=['status'])

        video_file_path = generate_summary_video(video_record.assessment, video_record.id)
        relative_path = video_file_path.replace('\\', '/')
        if relative_path.startswith('media/'):
            relative_path = relative_path[len('media/'):]

        video_record.video_file.name = relative_path
        video_record.status = 'completed'
        video_record.error_message = ''
        video_record.save(update_fields=['video_file', 'status', 'error_message'])
        print(f"Summary video generation for video_record {video_id} completed successfully.")

    except InterviewSummaryVideo.DoesNotExist:
        print(f"Task failed: InterviewSummaryVideo {video_id} not found.")
    except Exception as e:
        print(f"Summary video generation for video_record {video_id} failed: {e}")
        if video_record is not None:
            video_record.status = 'failed'
            video_record.error_message = str(e)
            video_record.save(update_fields=['status', 'error_message'])


# =============================================================================
# Feature #17: CV-based analysis task (Eye Contact, Posture, Distraction)
# Feature #18: Extends the same task to record timestamped events for replay
# =============================================================================

# ------------------------------------------------------------------------------
# HEURISTIC THRESHOLDS — adjust these constants after real-world calibration.
# They are intentionally grouped here (not buried in helpers) so they are easy
# to find and change without touching any scoring logic.
# ------------------------------------------------------------------------------

# Maximum angle (degrees) between gaze direction and the camera-forward vector
# to count a frame as "making eye contact".
# Smaller = stricter (candidate must look more directly at camera).
GAZE_ANGLE_THRESHOLD_DEG = 20

# Maximum angle (degrees) between the shoulder-to-hip spine vector and world-up
# to count a frame as "good posture" (upright, not slouched).
POSTURE_ANGLE_THRESHOLD_DEG = 35

# Normalised distance (MediaPipe [0,1] coords) between hand wrist and face centre
# below which we flag a "distraction" event (e.g. phone held close to face).
HAND_FACE_PROXIMITY_THRESHOLD = 0.08

# How many video frames to advance before sampling the next frame.
# At CV_SAMPLE_EVERY=1 we sample every second (1 fps sample rate).
# Increase this value (e.g. 2 = every 2 s) to trade accuracy for speed.
CV_SAMPLE_EVERY_N_SECONDS = 1


# ------------------------------------------------------------------------------
# Geometry helpers
# ------------------------------------------------------------------------------

def _landmark_to_np(landmark):
    """Convert a MediaPipe NormalizedLandmark to a NumPy (x, y, z) array."""
    import numpy as np
    return np.array([landmark.x, landmark.y, landmark.z], dtype=np.float32)


def _vector_angle_deg(v1, v2):
    """Return the angle in degrees between two 3-D vectors."""
    import numpy as np
    v1_u = v1 / (np.linalg.norm(v1) + 1e-8)
    v2_u = v2 / (np.linalg.norm(v2) + 1e-8)
    return float(np.degrees(np.arccos(np.clip(np.dot(v1_u, v2_u), -1.0, 1.0))))


# ------------------------------------------------------------------------------
# Per-frame scorer
# ------------------------------------------------------------------------------

def _score_frame(results, frame_num=0):
    """
    Evaluate a single MediaPipe-Holistic result and return boolean flags.

    Returns:
        dict with keys:
            eye_contact  (bool) – True when gaze angle ≤ GAZE_ANGLE_THRESHOLD_DEG
            good_posture (bool) – True when spine-vertical angle ≤ POSTURE_ANGLE_THRESHOLD_DEG
            distraction  (bool) – True when right-hand wrist is very close to face centre
        and:
            eye_center   (np.ndarray | None) – reused for distraction check
    """
    import numpy as np
    import mediapipe as mp

    face_mesh = mp.solutions.face_mesh
    pose_sol = mp.solutions.pose

    # ── 1. Eye contact ────────────────────────────────────────────────────────
    eye_contact = False
    eye_center = None
    gaze_angle_debug = None

    if results.face_landmarks:
        lm = results.face_landmarks.landmark
        # Use iris landmarks for more accurate gaze direction
        # Left iris center: landmark 468, Right iris center: landmark 473
        # These are available when refine_face_landmarks=True (default in Holistic)
        try:
            left_iris = _landmark_to_np(lm[468])
            right_iris = _landmark_to_np(lm[473])
            eye_center = (left_iris + right_iris) / 2.0

            # Use face center (between eyes) as reference for head orientation
            # Left eye corner: 33, Right eye corner: 263
            left_eye_corner = _landmark_to_np(lm[33])
            right_eye_corner = _landmark_to_np(lm[263])
            face_center = (left_eye_corner + right_eye_corner) / 2.0

            # Gaze vector: from face center through iris center
            # This approximates the direction the person is looking
            gaze_vec = eye_center - face_center

            # Camera-forward in MediaPipe's coordinate system points in the -Z direction.
            cam_fwd = np.array([0.0, 0.0, -1.0], dtype=np.float32)
            angle = _vector_angle_deg(gaze_vec, cam_fwd)
            gaze_angle_debug = angle

            eye_contact = angle <= GAZE_ANGLE_THRESHOLD_DEG
        except (IndexError, KeyError) as e:
            # Fallback to simpler method if iris landmarks unavailable
            left_eye = _landmark_to_np(lm[159])
            right_eye = _landmark_to_np(lm[386])
            eye_center = (left_eye + right_eye) / 2.0
            nose_tip = _landmark_to_np(lm[4])
            gaze_vec = nose_tip - eye_center
            cam_fwd = np.array([0.0, 0.0, -1.0], dtype=np.float32)
            angle = _vector_angle_deg(gaze_vec, cam_fwd)
            gaze_angle_debug = angle
            eye_contact = angle <= GAZE_ANGLE_THRESHOLD_DEG

    # ── 2. Posture ────────────────────────────────────────────────────────────
    good_posture = False
    posture_angle_debug = None

    if results.pose_landmarks:
        plm = results.pose_landmarks.landmark
        left_shoulder = _landmark_to_np(plm[pose_sol.PoseLandmark.LEFT_SHOULDER])
        right_shoulder = _landmark_to_np(plm[pose_sol.PoseLandmark.RIGHT_SHOULDER])
        left_hip = _landmark_to_np(plm[pose_sol.PoseLandmark.LEFT_HIP])
        right_hip = _landmark_to_np(plm[pose_sol.PoseLandmark.RIGHT_HIP])

        shoulder_mid = (left_shoulder + right_shoulder) / 2.0
        hip_mid = (left_hip + right_hip) / 2.0
        spine_vec = shoulder_mid - hip_mid   # points upward when upright

        # MediaPipe's coordinate system has Y increasing downward (screen coordinates).
        # Real-world "up" corresponds to negative Y, not positive Y.
        up = np.array([0.0, -1.0, 0.0], dtype=np.float32)
        angle = _vector_angle_deg(spine_vec, up)
        posture_angle_debug = angle

        good_posture = angle <= POSTURE_ANGLE_THRESHOLD_DEG

    # ── 3. Distraction (hand near face) ──────────────────────────────────────
    distraction = False

    if results.right_hand_landmarks and eye_center is not None:
        hlm = results.right_hand_landmarks.landmark
        import mediapipe.python.solutions.hands as hands_sol
        wrist = _landmark_to_np(hlm[hands_sol.HandLandmark.WRIST])
        dist = float(np.linalg.norm(wrist - eye_center))
        distraction = dist <= HAND_FACE_PROXIMITY_THRESHOLD

    return {
        "eye_contact": eye_contact,
        "good_posture": good_posture,
        "distraction": distraction,
    }


# ------------------------------------------------------------------------------
# Main background task
# ------------------------------------------------------------------------------

def process_cv_analysis_task(assessment_id):
    """
    Django-Q background task — Feature #17 + #18.

    Reads the interview video file belonging to Assessment <assessment_id>,
    samples it at CV_SAMPLE_EVERY_N_SECONDS fps using OpenCV, runs
    MediaPipe-Holistic on each sampled frame, and:

      * accumulates per-frame boolean hits to compute aggregate % scores
        (eye_contact_score, posture_score, gesture_score as distraction proxy)

      * records a timestamped event only on good→bad state transitions
        (avoids flooding; stored in AssessmentResult.cv_analysis_events)

    Collision safety: checks cv_analysis_status before starting and sets it to
    'processing' atomically — mirrors the generate_summary_video_task pattern.

    Does NOT auto-trigger itself; must be queued manually or via a view
    (wiring to the automatic flow is deferred until manual testing is confirmed).
    """
    import logging
    import os
    import uuid as _uuid

    logger = logging.getLogger(__name__)
    logger.info(f"[CV ANALYSIS TASK] Starting for Assessment {assessment_id}")

    # ── Import heavy dependencies here (lazy) ─────────────────────────────────
    try:
        import cv2
        import numpy as np
        import mediapipe as mp
    except ImportError as exc:
        logger.error(
            f"[CV ANALYSIS TASK] Missing dependency: {exc}. "
            "Install mediapipe and opencv-python."
        )
        return

    from django.db import transaction
    from .models import IndividualAssessment

    # ── 1. Fetch + status guard ───────────────────────────────────────────────
    try:
        assessment = IndividualAssessment.objects.get(id=assessment_id)
    except IndividualAssessment.DoesNotExist:
        logger.error(f"[CV ANALYSIS TASK] IndividualAssessment {assessment_id} not found.")
        return

    if assessment.cv_analysis_status in ('processing', 'completed'):
        logger.warning(
            f"[CV ANALYSIS TASK] IndividualAssessment {assessment.id} already "
            f"'{assessment.cv_analysis_status}'. Skipping duplicate dispatch."
        )
        return

    assessment.cv_analysis_status = 'processing'
    assessment.save(update_fields=['cv_analysis_status'])

    try:
        # ── 2. Validate responses with video files ────────────────────────────────
        responses_with_video = [
            r for r in assessment.responses.all().order_by('question_order') 
            if r.video_file and r.video_file.name
        ]

        if not responses_with_video:
            logger.error(f"[CV ANALYSIS TASK] IndividualAssessment {assessment_id} has no valid video responses.")
            assessment.cv_analysis_status = 'failed'
            assessment.save(update_fields=['cv_analysis_status'])
            return

        # Unique temp folder in case any intermediate files are needed.
        # Currently unused (we stream frames in-memory), but reserved for safety.
        first_video_path = responses_with_video[0].video_file.path
        temp_dir = os.path.join(
            os.path.dirname(first_video_path),
            f"cv_tmp_{_uuid.uuid4().hex}"
        )
        os.makedirs(temp_dir, exist_ok=True)

        # ── 4. Frame loop ─────────────────────────────────────────────────────────
        global_eye_contact_hits = 0
        global_posture_hits = 0
        global_distraction_hits = 0
        global_processed_frames = 0
        events = []  # Feature #18: timestamped state-transition events

        logger.info(
            f"[CV ANALYSIS TASK] Video: processing {len(responses_with_video)} responses."
        )

        with mp.solutions.holistic.Holistic(
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
                refine_face_landmarks=True  # Required for iris landmarks (468-477)
            ) as holistic:

                for response in responses_with_video:
                    try:
                        video_path = response.video_file.path
                        if not os.path.exists(video_path):
                            logger.warning(f"[CV ANALYSIS TASK] Video missing for response {response.id}, skipping.")
                            continue
                    except (ValueError, NotImplementedError):
                        continue

                    cap = cv2.VideoCapture(video_path)
                    if not cap.isOpened():
                        logger.warning(f"[CV ANALYSIS TASK] OpenCV could not open: {video_path}")
                        continue

                    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                    frame_interval = max(1, int(round(fps * CV_SAMPLE_EVERY_N_SECONDS)))

                    frame_idx = 0
                    prev_eye = True
                    prev_posture = True
                    prev_distraction = False

                    try:
                        while True:
                            ret, frame = cap.read()
                            if not ret:
                                break

                            if frame_idx % frame_interval == 0:
                                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                                scores = _score_frame(holistic.process(rgb), global_processed_frames)

                                global_processed_frames += 1
                                if scores['eye_contact']: global_eye_contact_hits += 1
                                if scores['good_posture']: global_posture_hits += 1
                                if scores['distraction']: global_distraction_hits += 1

                                timestamp_sec = int(frame_idx / fps)

                                # Event logging: log on good -> bad transitions
                                if prev_eye and not scores['eye_contact']:
                                    events.append({
                                        "response_id": response.id,
                                        "question_order": response.question_order,
                                        "timestamp_sec": timestamp_sec,
                                        "type": "eye_contact_drop"
                                    })
                                if prev_posture and not scores['good_posture']:
                                    events.append({
                                        "response_id": response.id,
                                        "question_order": response.question_order,
                                        "timestamp_sec": timestamp_sec,
                                        "type": "posture_drop"
                                    })
                                if not prev_distraction and scores['distraction']:
                                    events.append({
                                        "response_id": response.id,
                                        "question_order": response.question_order,
                                        "timestamp_sec": timestamp_sec,
                                        "type": "distraction"
                                    })

                                prev_eye = scores['eye_contact']
                                prev_posture = scores['good_posture']
                                prev_distraction = scores['distraction']

                            frame_idx += 1
                    finally:
                        cap.release()

        # Cleanup temp folder (nothing was written, but tidy up)
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

        if global_processed_frames == 0:
            logger.error("[CV ANALYSIS TASK] Zero frames were processed — aborting.")
            assessment.cv_analysis_status = 'failed'
            assessment.save(update_fields=['cv_analysis_status'])
            return

        # ── 5. Compute aggregate scores ───────────────────────────────────────────
        eye_contact_score = round((global_eye_contact_hits / global_processed_frames) * 100, 2)
        posture_score = round((global_posture_hits / global_processed_frames) * 100, 2)
        # gesture_score repurposed as distraction proxy: % of frames with distraction
        gesture_score = round((global_distraction_hits / global_processed_frames) * 100, 2)

        logger.info(
            f"[CV ANALYSIS TASK] Results — {global_processed_frames} frames sampled. "
            f"eye_contact={eye_contact_score}%, posture={posture_score}%, "
            f"distraction(gesture)={gesture_score}%, events={len(events)}"
        )

        # ── 6. Persist results atomically ─────────────────────────────────────────
        with transaction.atomic():
            assessment.eye_contact_score = eye_contact_score
            assessment.posture_score = posture_score
            assessment.gesture_score = gesture_score          # distraction proxy
            assessment.cv_analysis_events = events            # Feature #18 timeline
            assessment.cv_analysis_status = 'completed'
            assessment.save(update_fields=[
                'eye_contact_score',
                'posture_score',
                'gesture_score',
                'cv_analysis_events',
                'cv_analysis_status',
            ])
        logger.info(
            f"[CV ANALYSIS TASK] IndividualAssessment {assessment.id} saved. "
            f"{len(events)} timeline events stored."
        )

    except Exception as exc:
        logger.exception(
            f"[CV ANALYSIS TASK] Failed to process CV analysis for IndividualAssessment {assessment.id}: {exc}"
        )
        assessment.cv_analysis_status = 'failed'
        assessment.save(update_fields=['cv_analysis_status'])


# =============================================================================
# Media Retention Cleanup Task
# =============================================================================

def cleanup_old_media_task():
    """
    Django-Q background task for media retention cleanup.
    
    For each user, finds IndividualAssessmentResponse and Assessment records
    where created_at is older than the user's media_retention_days setting,
    and deletes only the video_file and audio_file fields (keeps DB records).
    
    Logs how many files were cleaned up per run.
    """
    import logging
    from django.utils import timezone
    from django.db import transaction
    from django.contrib.auth import get_user_model
    from .models import IndividualAssessmentResponse, Assessment
    
    logger = logging.getLogger(__name__)
    logger.info("[MEDIA CLEANUP TASK] Starting media retention cleanup")
    
    User = get_user_model()
    
    total_video_files_deleted = 0
    total_audio_files_deleted = 0
    total_users_processed = 0
    
    try:
        # Get all individual users
        individual_users = User.objects.filter(individual_profile__isnull=False)
        
        for user in individual_users:
            try:
                profile = user.individual_profile
                retention_days = profile.media_retention_days
                cutoff_date = timezone.now() - timezone.timedelta(days=retention_days)
                
                user_video_deleted = 0
                user_audio_deleted = 0
                
                # Clean up IndividualAssessmentResponse media files
                old_responses = IndividualAssessmentResponse.objects.filter(
                    assessment__user=user,
                    created_at__lt=cutoff_date
                )
                
                for response in old_responses:
                    # Delete video file if exists
                    if response.video_file and response.video_file.name:
                        try:
                            response.video_file.delete(save=False)
                            user_video_deleted += 1
                            logger.debug(f"[MEDIA CLEANUP] Deleted video file for response {response.id}")
                        except Exception as e:
                            logger.warning(f"[MEDIA CLEANUP] Failed to delete video file for response {response.id}: {e}")
                    
                    # Delete audio file if exists
                    if response.audio_file and response.audio_file.name:
                        try:
                            response.audio_file.delete(save=False)
                            user_audio_deleted += 1
                            logger.debug(f"[MEDIA CLEANUP] Deleted audio file for response {response.id}")
                        except Exception as e:
                            logger.warning(f"[MEDIA CLEANUP] Failed to delete audio file for response {response.id}: {e}")
                    
                    # Save response to clear file fields
                    response.save(update_fields=['video_file', 'audio_file'])
                
                # Clean up Assessment.video_file (old-style, future-proofing)
                old_assessments = Assessment.objects.filter(
                    user=user,
                    assessment_type='individual',
                    created_at__lt=cutoff_date,
                    video_file__isnull=False
                ).exclude(video_file='')
                
                for assessment in old_assessments:
                    if assessment.video_file and assessment.video_file.name:
                        try:
                            assessment.video_file.delete(save=False)
                            user_video_deleted += 1
                            logger.debug(f"[MEDIA CLEANUP] Deleted video file for assessment {assessment.id}")
                            assessment.save(update_fields=['video_file'])
                        except Exception as e:
                            logger.warning(f"[MEDIA CLEANUP] Failed to delete video file for assessment {assessment.id}: {e}")
                
                if user_video_deleted > 0 or user_audio_deleted > 0:
                    total_users_processed += 1
                    total_video_files_deleted += user_video_deleted
                    total_audio_files_deleted += user_audio_deleted
                    logger.info(
                        f"[MEDIA CLEANUP] User {user.email}: "
                        f"deleted {user_video_deleted} video files, {user_audio_deleted} audio files "
                        f"(retention: {retention_days} days)"
                    )
                
            except Exception as e:
                logger.error(f"[MEDIA CLEANUP] Error processing user {user.email}: {e}")
                continue
        
        logger.info(
            f"[MEDIA CLEANUP TASK] Completed. "
            f"Processed {total_users_processed} users, "
            f"deleted {total_video_files_deleted} video files, "
            f"{total_audio_files_deleted} audio files total"
        )
        
    except Exception as e:
        logger.exception(f"[MEDIA CLEANUP TASK] Failed: {e}")

