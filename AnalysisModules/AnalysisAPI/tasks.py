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

        video_path = response.video_file.path
        if not os.path.exists(video_path):
            print(f"Speech analysis skipped for response {response_id}: video file not found at {video_path}")
            return

        # Groq's hosted whisper-large-v3 accepts the recorded .webm container
        # directly, so no local ffmpeg audio extraction is needed.
        with open(video_path, 'rb') as f:
            audio_bytes = f.read()

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
GAZE_ANGLE_THRESHOLD_DEG = 20  # Legacy threshold — CV now runs client-side (informational only)

# Maximum angle (degrees) between the shoulder-to-hip spine vector and world-up
# to count a frame as "good posture" (upright, not slouched).
POSTURE_ANGLE_THRESHOLD_DEG = 35  # Legacy threshold — CV now runs client-side (informational only)

# Normalised distance (MediaPipe [0,1] coords) between hand wrist and face centre
# below which we flag a "distraction" event (e.g. phone held close to face).
HAND_FACE_PROXIMITY_THRESHOLD = 0.08  # Legacy threshold — CV now runs client-side (informational only)

# How many video frames to advance before sampling the next frame.
# At CV_SAMPLE_EVERY=1 we sample every second (1 fps sample rate).
# Increase this value (e.g. 2 = every 2 s) to trade accuracy for speed.
CV_SAMPLE_EVERY_N_SECONDS = 1  # Legacy — video frames are no longer sampled server-side


# ------------------------------------------------------------------------------
# Geometry helpers
# ------------------------------------------------------------------------------

def _landmark_to_np(landmark):  # noqa: kept for backwards compatibility with legacy imports
    """Convert a MediaPipe NormalizedLandmark to a NumPy (x, y, z) array."""
    import numpy as np
    return np.array([landmark.x, landmark.y, landmark.z], dtype=np.float32)


def _vector_angle_deg(v1, v2):  # noqa: kept for backwards compatibility with legacy imports
    """Return the angle in degrees between two 3-D vectors."""
    import numpy as np
    v1_u = v1 / (np.linalg.norm(v1) + 1e-8)
    v2_u = v2 / (np.linalg.norm(v2) + 1e-8)
    return float(np.degrees(np.arccos(np.clip(np.dot(v1_u, v2_u), -1.0, 1.0))))


# ------------------------------------------------------------------------------
# Per-frame scorer
# ------------------------------------------------------------------------------

def _score_frame(results, frame_num=0):  # noqa: legacy helper — CV now runs client-side
    """Evaluate a single MediaPipe-Holistic result and return boolean flags.

    REMOVED: proctoring now runs in-browser (MediaPipe Tasks Vision / WASM), so
    the server no longer samples video frames. This stub exists only so that
    any stale import keeps working; the caller should never reach it.
    """
    raise NotImplementedError('Server-side frame scoring removed; proctoring runs in-browser')


# ------------------------------------------------------------------------------
# Main background task
# ------------------------------------------------------------------------------

def process_cv_analysis_task(assessment_id):
    """
    Django-Q background task — Feature #17 + #18 (client-side proctoring era).

    Proctoring detection (face presence, multiple faces, phone/object) now runs
    in-browser via MediaPipe Tasks Vision (WASM) and is reported to the server
    as small JSON events saved into EnvironmentIntegrityEvent. There is no more
    server-side OpenCV/MediaPipe frame processing, so cv2/mediapipe are no
    longer required dependencies.

    This task therefore derives the same aggregate CV metrics that the old
    frame-processing loop produced, but from the client-reported integrity
    events:
      * eye_contact_score  = % of presence checks that reported a face
                             (no_face_detected rate inverted)
      * posture_score      = inverse-weighted score based on violation events
                             (multiple faces / phone / device switches)
      * gesture_score      = % of logged events that were object/phone
                             detections (distraction proxy)
      * cv_analysis_events = compact timeline of all environment integrity
                             events, mirroring the old state-transition events
    Collision safety: checks cv_analysis_status before starting and sets it to
    'processing' atomically — mirrors the generate_summary_video_task pattern.
    """
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[CV ANALYSIS TASK] Starting for Assessment {assessment_id}")
    from django.db import transaction
    from .models import IndividualAssessment, EnvironmentIntegrityEvent
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
        # ── 2. Gather client-reported events ──────────────────────────────────────
        # presence checks = face-check events (presence reports) for this session.
        # Face-check pings that reported a healthy face produce no event row,
        # so presence quality is measured by the absence of no_face_detected
        # events: with a check every ~50s, an event ratio relative to a
        # normalized check count approximates the old frame-hit rate.
        events_qs = EnvironmentIntegrityEvent.objects.filter(assessment=assessment)
        total_events = events_qs.count()
        face_events = events_qs.filter(event_type__in=(
            'no_face_detected', 'multiple_faces_detected',
        ))
        no_face_events = events_qs.filter(event_type='no_face_detected')
        object_events = events_qs.filter(event_type__in=(
            'phone_detected', 'multiple_faces_detected',
        ))

        # Normalize: assume one presence check per 50 seconds of active
        # assessment time. If duration is unavailable fall back to 24 checks
        # (a 20-minute interview at the default 50s interval).
        started_at = getattr(assessment, 'started_at', None) or getattr(assessment, 'created_at', None)
        finished_at = getattr(assessment, 'completed_at', None) or None
        try:
            if started_at and finished_at:
                duration_sec = max((finished_at - started_at).total_seconds(), 60)
            else:
                duration_sec = 20 * 60
        except Exception:
            duration_sec = 20 * 60
        normalized_checks = max(round(duration_sec / 50), 1)

        if total_events == 0:
            # No proctoring events at all → a clean session
            eye_contact_score = 100.0
            posture_score = 100.0
            gesture_score = 0.0
            events = []
        else:
            # Eye contact: % of normalized checks that kept a face visible
            eye_contact_score = round(
                max(0.0, (1 - no_face_events.count() / normalized_checks)) * 100, 2
            )
            # Posture / environment: penalize per violation event (heavier
            # penalty for multiple-face events than for a single no-face blip)
            posture_penalty = min(
                100.0,
                (no_face_events.count() * 2 + face_events.exclude(event_type='no_face_detected').count() * 8) /
                normalized_checks * 25
            )
            posture_score = round(max(0.0, 100.0 - posture_penalty), 2)
            # Distraction proxy: share of violation events that were objects
            gesture_score = round(
                object_events.count() / total_events * 100 if total_events else 0.0, 2
            )
            # Timeline mirroring the old good→bad transition events
            events = [
                {
                    'question_order': None,
                    'response_id': None,
                    'timestamp_sec': int((e.timestamp - started_at).total_seconds()) if started_at else None,
                    'type': e.event_type,
                    'details': e.details,
                }
                for e in events_qs.order_by('timestamp')
            ]

        logger.info(
            f"[CV ANALYSIS TASK] Derived from {total_events} client-reported events "
            f"({normalized_checks} normalized checks): eye_contact={eye_contact_score}%, "
            f"posture={posture_score}%, distraction(gesture)={gesture_score}%"
        )

        # ── 6. Persist results atomically ─────────────────────────────────────────
        with transaction.atomic():
            assessment.eye_contact_score = eye_contact_score
            assessment.posture_score = posture_score
            assessment.gesture_score = gesture_score          # distraction proxy
            assessment.cv_analysis_events = events            # timeline
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

