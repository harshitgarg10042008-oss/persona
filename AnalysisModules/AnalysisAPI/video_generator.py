import os
import textwrap
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS

try:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
except ImportError:
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

def _truncate(text, max_len=100):
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    truncated = text[:max_len].rsplit(' ', 1)[0]
    return truncated + "..."

def generate_summary_video(assessment, video_record_id):
    """
    Takes an IndividualAssessment instance and the InterviewSummaryVideo PK.
    Uses video_record_id in all temp and output file names so that concurrent
    workers processing different records for the same assessment never collide.
    Returns the file path of the generated MP4 on success, or raises an
    exception on failure (caller will handle try/except).
    """
    record_id = str(video_record_id)
    output_dir = os.path.join("media", "summary_videos")
    os.makedirs(output_dir, exist_ok=True)
    output_filepath = os.path.join(output_dir, f"{record_id}_summary.mp4")

    temp_files = []
    
    try:
        job_title = "Assessment"
        if assessment.platform_job_title:
            job_title = assessment.platform_job_title.title

        slides_data = []

        # Slide 1: Intro
        intro_text = f"Interview Summary\n\n{job_title}"
        intro_narration = f"Here is your interview summary for the {job_title} role."
        slides_data.append((intro_text, intro_narration))

        # Slide 2: Overall Score
        score = assessment.overall_score
        score_display = f"{score:.1f}/10" if score is not None else "N/A"
        overall_text = f"Overall Score\n\n{score_display}"
        overall_narration = f"Your overall performance score is {score_display}."
        slides_data.append((overall_text, overall_narration))

        # Slide 3: Detailed Scores
        spk = assessment.speaking_score
        bdl = assessment.body_language_score
        att = assessment.attire_score
        
        spk_disp = f"{spk:.1f}/10" if spk is not None else "N/A"
        bdl_disp = f"{bdl:.1f}/10" if bdl is not None else "N/A"
        att_disp = f"{att:.1f}/10" if att is not None else "N/A"

        detailed_text = f"Speaking: {spk_disp}\nBody Language: {bdl_disp}\nAttire: {att_disp}"
        detailed_narration = "Here is the breakdown of your speaking, body language, and attire scores."
        slides_data.append((detailed_text, detailed_narration))

        # Slide 4: Strengths
        strengths = []
        if assessment.skill_gap_analysis and isinstance(assessment.skill_gap_analysis, dict):
            strengths = assessment.skill_gap_analysis.get('strengths', [])
        if not strengths and assessment.ai_coach_strengths:
            strengths = assessment.ai_coach_strengths
            
        if strengths and isinstance(strengths, list) and len(strengths) > 0:
            top_strengths = strengths[:2]
            clean_str = []
            for s in top_strengths:
                raw_str = str(s)
                truncated_str = _truncate(raw_str, max_len=100)
                wrapped_str = textwrap.fill(truncated_str, width=45)
                clean_str.append(wrapped_str)
            
            text = "Top Strengths\n\n• " + "\n• ".join(clean_str)
            narration_parts = [s.replace('\n', ' ') for s in clean_str]
            narration = "Your top strengths included: " + ", and ".join(narration_parts) + "."
            slides_data.append((text, narration))

        # Slide 5: Improvement Areas
        improvements = []
        if assessment.skill_gap_analysis and isinstance(assessment.skill_gap_analysis, dict):
            improvements = assessment.skill_gap_analysis.get('gaps', assessment.skill_gap_analysis.get('weaknesses', []))
        if not improvements and assessment.ai_coach_weaknesses:
            improvements = assessment.ai_coach_weaknesses
            
        if improvements and isinstance(improvements, list) and len(improvements) > 0:
            top_imps = improvements[:2]
            clean_imp = []
            for i in top_imps:
                raw_imp = str(i)
                truncated_imp = _truncate(raw_imp, max_len=100)
                wrapped_imp = textwrap.fill(truncated_imp, width=45)
                clean_imp.append(wrapped_imp)
                    
            text = "Areas for Improvement\n\n• " + "\n• ".join(clean_imp)
            narration_parts = [i.replace('\n', ' ') for i in clean_imp]
            narration = "Your main areas for improvement are: " + ", and ".join(narration_parts) + "."
            slides_data.append((text, narration))

        # Slide 6: Closing
        closing_text = "Keep Practicing!"
        closing_narration = "Keep practicing! You are doing great."
        slides_data.append((closing_text, closing_narration))

        # Generate media
        clips = []

        for idx, (text, narration) in enumerate(slides_data):
            print(f"Generating slide {idx} with text:\n{text}\n")
            
            # Pillow image
            img = Image.new('RGB', (1280, 720), color=(41, 43, 47))
            d = ImageDraw.Draw(img)
            
            is_bullet_slide = "Top Strengths" in text or "Areas for Improvement" in text
            font_size = 38 if is_bullet_slide else 60
            
            font = None
            for font_name in ["arial.ttf", "segoeui.ttf", "calibri.ttf"]:
                try:
                    font = ImageFont.truetype(font_name, font_size)
                    break
                except IOError:
                    continue
            if not font:
                font = ImageFont.load_default()

            try:
                bbox = d.multiline_textbbox((0, 0), text, font=font, align="center")
                text_w = bbox[2] - bbox[0]
                text_h = bbox[3] - bbox[1]
            except AttributeError:
                try:
                    text_w, text_h = d.textsize(text, font=font)
                except AttributeError:
                    text_w, text_h = 800, 200  # Fallback

            x = (1280 - text_w) / 2
            y = (720 - text_h) / 2
            
            d.multiline_text((x, y), text, fill=(255, 255, 255), font=font, align="center")
            
            img_path = os.path.join(output_dir, f"temp_{record_id}_{idx}.png")
            img.save(img_path)
            temp_files.append(img_path)

            # gTTS audio
            tts = gTTS(text=narration, lang='en', slow=False)
            audio_path = os.path.join(output_dir, f"temp_{record_id}_{idx}.mp3")
            tts.save(audio_path)
            temp_files.append(audio_path)

            # MoviePy clips
            audio_clip = AudioFileClip(audio_path)
            image_clip = ImageClip(img_path)
            
            # Version-agnostic syntax for Moviepy v1.x and v2.x
            if hasattr(image_clip, 'with_duration'):
                image_clip = image_clip.with_duration(audio_clip.duration)
            else:
                image_clip = image_clip.set_duration(audio_clip.duration)
                
            if hasattr(image_clip, 'with_audio'):
                video_clip = image_clip.with_audio(audio_clip)
            else:
                video_clip = image_clip.set_audio(audio_clip)
            
            clips.append(video_clip)

        # Write final video
        final_video = concatenate_videoclips(clips, method="compose")
        final_video.write_videofile(
            output_filepath, 
            fps=24, 
            codec="libx264", 
            audio_codec="aac"
        )
        
        # Free resources
        final_video.close()
        for c in clips:
            c.close()

        return output_filepath

    finally:
        # Cleanup temporary files safely
        for temp_file in temp_files:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass
