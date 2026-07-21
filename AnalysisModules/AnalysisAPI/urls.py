from django.urls import path
from . import views

app_name = 'analysis'

urlpatterns = [
    # Business Dashboard
    path('dashboard/', views.business_dashboard, name='business_dashboard'),
    
    # Job Role Management
    path('job-roles/create/', views.create_job_role, name='create_job_role'),
    path('job-roles/<int:job_role_id>/', views.job_role_detail, name='job_role_detail'),
    path('job-roles/<int:job_role_id>/results/', views.assessment_results, name='assessment_results'),
    path('job-roles/<int:role_id>/export/', views.export_role_candidates_csv, name='export_role_candidates_csv'),

    
    # Question Management
    path('job-roles/<int:job_role_id>/add-question/', views.add_question, name='add_question'),
    
    # Assessment Link Management
    path('job-roles/<int:job_role_id>/generate-link/', views.generate_assessment_link, name='generate_assessment_link'),
    
    # Public Assessment Taking
    path('assessment/<str:link_id>/', views.take_assessment, name='take_assessment'),
    path('assessment-complete/<int:assessment_id>/', views.assessment_complete, name='assessment_complete'),
    
    # Business Assessment System (Integrated Combined Assessment)
    path('business-assessment/<int:assessment_id>/combined/', views.business_combined_assessment, name='business_combined_assessment'),
    path('business-assessment/<int:assessment_id>/complete/', views.business_assessment_complete, name='business_assessment_complete'),
    path('business-snapshot/<int:assessment_id>/', views.business_capture_snapshot, name='business_capture_snapshot'),
    path('business-response/<int:assessment_id>/', views.business_submit_response, name='business_submit_response'),
    
    # Individual Assessment System
    path('individual/', views.individual_dashboard, name='individual_dashboard'),
    path('individual/start/', views.start_individual_assessment, name='start_individual_assessment'),
    path('individual/<uuid:session_id>/setup/', views.individual_assessment_setup, name='individual_assessment_setup'),
    path('individual/<uuid:session_id>/start-session/', views.start_individual_assessment_session, name='start_individual_assessment_session'),
    path('individual/<uuid:session_id>/question/', views.individual_assessment_question, name='individual_assessment_question'),
    path('individual/<uuid:session_id>/submit/', views.submit_assessment_response, name='submit_assessment_response'),
    path('individual/<uuid:session_id>/snapshot/', views.capture_assessment_snapshot, name='capture_assessment_snapshot'),
    path('individual/<uuid:session_id>/processing/', views.processing_interstitial, name='processing_interstitial'),
    path('individual/<uuid:session_id>/processing-status/', views.check_processing_status, name='check_processing_status'),
    path('individual/<uuid:session_id>/complete/', views.complete_individual_assessment, name='complete_individual_assessment'),
    path('individual/<uuid:session_id>/pdf/', views.download_assessment_report, name='download_assessment_report'),
    
    # Combined Assessment System (Setup + Questions)
    path('assessment/<uuid:session_id>/combined/', views.combined_assessment, name='combined_assessment'),
    path('combined-snapshot/<uuid:session_id>/', views.capture_snapshot_combined, name='capture_snapshot_combined'),
    path('combined-response/<uuid:session_id>/', views.submit_response_combined, name='submit_response_combined'),
    # Legacy alias kept so older processing_results.html / bookmarks still resolve
    path('processing-status/<uuid:session_id>/', views.check_processing_status, name='check_processing_status_legacy'),
    path('assessment/<uuid:session_id>/processing/', views.processing_interstitial, name='processing_interstitial_legacy'),
    
    # Clean Assessment System (New Implementation)
    path('assessment/<uuid:session_id>/clean/', views.clean_assessment_question, name='clean_assessment_question'),
    path('capture-snapshot/<uuid:session_id>/', views.capture_snapshot_clean, name='capture_snapshot_clean'),
    path('submit-response/<uuid:session_id>/', views.submit_response_clean, name='submit_response_clean'),
    
    path('individual/<uuid:session_id>/abandon/', views.abandon_assessment, name='abandon_assessment'),
    path('history/', views.assessment_history, name='assessment_history'),
    
    # Achievement Badges
    path('badge/<uuid:session_id>/', views.achievement_badge, name='achievement_badge'),
    path('badge/<uuid:session_id>/download/', views.download_achievement_badge, name='download_achievement_badge'),
    
    # Institution Management
    path('export-institution-members/', views.export_institution_members_csv, name='export_institution_members_csv'),
    
    # Resume Reviewer
    path('resume-reviewer/upload/', views.resume_reviewer_upload, name='resume_reviewer_upload'),
    path('resume-reviewer/result/<int:review_id>/', views.resume_reviewer_result, name='resume_reviewer_result'),
    path('resume-reviewer/history/', views.resume_reviewer_history, name='resume_reviewer_history'),
    
    # Cover Letter Generator
    path('cover-letter/generate/', views.cover_letter_generate, name='cover_letter_generate'),
    path('cover-letter/result/<int:letter_id>/', views.cover_letter_result, name='cover_letter_result'),
    path('cover-letter/history/', views.cover_letter_history, name='cover_letter_history'),
    
    # LinkedIn Post Generator
    path('linkedin-post/generate/', views.linkedin_post_generate, name='linkedin_post_generate'),
    path('linkedin-post/result/<int:post_id>/', views.linkedin_post_result, name='linkedin_post_result'),
    path('linkedin-post/history/', views.linkedin_post_history, name='linkedin_post_history'),

    # Interview Summary Video
    path('summary-video/generate/', views.interview_summary_video_generate, name='interview_summary_video_generate'),
    path('summary-video/status/<int:video_id>/', views.interview_summary_video_status, name='interview_summary_video_status'),
    path('summary-video/result/<int:video_id>/', views.interview_summary_video_result, name='interview_summary_video_result'),
]