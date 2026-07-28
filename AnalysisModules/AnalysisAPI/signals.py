from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.db import models
import os
from django.conf import settings


@receiver(pre_delete, sender='AnalysisAPI.IndividualAssessment')
def cleanup_individual_assessment_files(sender, instance, **kwargs):
    """
    Clean up all media files associated with an IndividualAssessment before deletion.
    This must run in pre_delete because once CASCADE removes the related rows,
    we lose the file paths.
    """
    # Clean up IndividualAssessmentResponse files (audio/video)
    for response in instance.responses.all():
        if response.audio_file and response.audio_file.name:
            response.audio_file.delete(save=False)
        if response.video_file and response.video_file.name:
            response.video_file.delete(save=False)
    
    # Clean up FollowUpResponse files (audio/video)
    for response in instance.responses.all():
        for follow_up in response.follow_ups.all():
            if follow_up.audio_file and follow_up.audio_file.name:
                follow_up.audio_file.delete(save=False)
            if follow_up.video_file and follow_up.video_file.name:
                follow_up.video_file.delete(save=False)
    
    # Clean up AssessmentSnapshot files (images)
    for snapshot in instance.snapshots.all():
        if snapshot.image_file and snapshot.image_file.name:
            snapshot.image_file.delete(save=False)
    
    # Clean up InterviewSummaryVideo files
    for summary_video in instance.summary_videos.all():
        if summary_video.video_file and summary_video.video_file.name:
            summary_video.video_file.delete(save=False)


@receiver(pre_delete, sender='AnalysisAPI.ResumeReview')
def cleanup_resume_review_files(sender, instance, **kwargs):
    """
    Clean up resume file associated with a ResumeReview before deletion.
    """
    if instance.resume_file and instance.resume_file.name:
        instance.resume_file.delete(save=False)
