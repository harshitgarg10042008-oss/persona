from django.contrib import admin
from .models import (
    PlatformJobTitle,
    PlatformQuestion,
    CompanyProfile,
    JobRole,
    InterviewQuestion,
    AssessmentLink,
    Assessment,
    AssessmentResult,
    IndividualAssessment,
    IndividualAssessmentResponse,
    PanelSession,
    PanelPersonaScore,
    FollowUpResponse,
    AssessmentSnapshot,
    BusinessAssessmentResponse,
    BusinessAssessmentSnapshot,
    ResumeReview,
    CoverLetter,
    LinkedInPost,
    InterviewSummaryVideo,
    CareerIntake,
    PlacementDrive,
)


# ─── PlatformJobTitle ─────────────────────────────────────────────────────────

@admin.register(PlatformJobTitle)
class PlatformJobTitleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'is_active', 'question_count', 'created_at')
    list_filter = ('category', 'is_active')
    search_fields = ('title', 'description')
    ordering = ('category', 'title')

    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'


# ─── PlatformQuestion ─────────────────────────────────────────────────────────

@admin.register(PlatformQuestion)
class PlatformQuestionAdmin(admin.ModelAdmin):
    list_display = ('job_title', 'order', 'question_type', 'difficulty_level', 'is_mandatory', 'is_active')
    list_filter = ('question_type', 'difficulty_level', 'is_mandatory', 'is_active', 'job_title')
    search_fields = ('question_text', 'job_title__title')
    ordering = ('job_title', 'order')
    list_editable = ('order', 'is_mandatory', 'is_active')


# ─── CompanyProfile ───────────────────────────────────────────────────────────

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'industry', 'created_at', 'updated_at')
    list_filter = ('industry',)
    search_fields = ('name', 'industry')
    ordering = ('name',)


# ─── JobRole ──────────────────────────────────────────────────────────────────

@admin.register(JobRole)
class JobRoleAdmin(admin.ModelAdmin):
    list_display = ('title', 'business_user', 'question_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'business_user__company_name')
    ordering = ('-created_at',)

    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'


# ─── InterviewQuestion ────────────────────────────────────────────────────────

@admin.register(InterviewQuestion)
class InterviewQuestionAdmin(admin.ModelAdmin):
    list_display = ('job_role', 'order', 'question_type', 'difficulty_level')
    list_filter = ('question_type', 'difficulty_level', 'job_role')
    search_fields = ('question_text', 'job_role__title')
    ordering = ('job_role', 'order')


# ─── AssessmentLink ───────────────────────────────────────────────────────────

@admin.register(AssessmentLink)
class AssessmentLinkAdmin(admin.ModelAdmin):
    list_display = ('job_role', 'access_code', 'is_active', 'expires_at', 'created_at')
    list_filter = ('is_active', 'expires_at')
    search_fields = ('access_code', 'job_role__title')
    readonly_fields = ('unique_link', 'access_code', 'created_at')
    ordering = ('-created_at',)


# ─── Assessment ───────────────────────────────────────────────────────────────

@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        'assessment_type',
        'display_user',
        'candidate_name',
        'job_title',
        'status',
        'started_at',
        'completed_at',
    )
    list_filter = ('assessment_type', 'status', 'started_at')
    search_fields = (
        'user__email',
        'candidate_name',
        'candidate_email',
        'job_title',
    )
    readonly_fields = ('started_at', 'completed_at', 'created_at')
    ordering = ('-created_at',)

    def display_user(self, obj):
        if obj.user:
            return obj.user.email
        return '—'
    display_user.short_description = 'User'


# ─── AssessmentResult ─────────────────────────────────────────────────────────

@admin.register(AssessmentResult)
class AssessmentResultAdmin(admin.ModelAdmin):
    list_display = (
        'assessment',
        'overall_score',
        'confidence_score',
        'attire_appropriateness',
        'cv_analysis_status',
        'analyzed_at',
    )
    list_filter = ('attire_appropriateness', 'cv_analysis_status', 'analyzed_at')
    search_fields = ('assessment__user__email', 'assessment__candidate_name')
    readonly_fields = ('analyzed_at',)
    ordering = ('-analyzed_at',)


# ─── IndividualAssessment ─────────────────────────────────────────────────────

@admin.register(IndividualAssessment)
class IndividualAssessmentAdmin(admin.ModelAdmin):
    list_display = (
        'user_email',
        'platform_job_title',
        'status',
        'overall_score',
        'interview_mode',
        'current_difficulty',
        'started_at',
        'completed_at',
    )
    list_filter = (
        'status',
        'interview_mode',
        'current_difficulty',
        'cv_analysis_status',
        'ai_coach_status',
        'started_at',
    )
    search_fields = ('user__email', 'user__username', 'platform_job_title__title')
    readonly_fields = (
        'session_id', 'started_at', 'completed_at', 'created_at', 'updated_at',
    )
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'


# ─── IndividualAssessmentResponse ─────────────────────────────────────────────

@admin.register(IndividualAssessmentResponse)
class IndividualAssessmentResponseAdmin(admin.ModelAdmin):
    list_display = (
        'user_email',
        'question_order',
        'question_difficulty',
        'response_duration',
        'relevance_score',
        'confidence_score',
        'created_at',
    )
    list_filter = ('question__difficulty_level', 'created_at')
    search_fields = ('assessment__user__email',)
    readonly_fields = ('created_at',)
    ordering = ('assessment', 'question_order')

    def user_email(self, obj):
        return obj.assessment.user.email
    user_email.short_description = 'User'

    def question_difficulty(self, obj):
        return obj.question.difficulty_level
    question_difficulty.short_description = 'Difficulty'


# ─── PanelSession ─────────────────────────────────────────────────────────────

@admin.register(PanelSession)
class PanelSessionAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'aggregated_score', 'created_at')
    search_fields = ('assessment__user__email',)
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)


# ─── PanelPersonaScore ────────────────────────────────────────────────────────

@admin.register(PanelPersonaScore)
class PanelPersonaScoreAdmin(admin.ModelAdmin):
    list_display = ('panel_session', 'persona_id', 'score', 'created_at')
    search_fields = ('persona_id',)
    ordering = ('-created_at',)


# ─── FollowUpResponse ─────────────────────────────────────────────────────────

@admin.register(FollowUpResponse)
class FollowUpResponseAdmin(admin.ModelAdmin):
    list_display = ('parent_response', 'created_at')
    search_fields = ('follow_up_prompt',)
    ordering = ('-created_at',)


# ─── AssessmentSnapshot ───────────────────────────────────────────────────────

@admin.register(AssessmentSnapshot)
class AssessmentSnapshotAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'analysis_type', 'score', 'timestamp')
    list_filter = ('analysis_type',)
    search_fields = ('assessment__user__email',)
    ordering = ('-created_at',)


# ─── BusinessAssessmentResponse ───────────────────────────────────────────────

@admin.register(BusinessAssessmentResponse)
class BusinessAssessmentResponseAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'question_order', 'response_duration', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('assessment__candidate_name', 'assessment__candidate_email')
    ordering = ('assessment', 'question_order')


# ─── BusinessAssessmentSnapshot ───────────────────────────────────────────────

@admin.register(BusinessAssessmentSnapshot)
class BusinessAssessmentSnapshotAdmin(admin.ModelAdmin):
    list_display = ('assessment', 'analysis_type', 'score', 'timestamp')
    list_filter = ('analysis_type',)
    ordering = ('-created_at',)


# ─── ResumeReview ─────────────────────────────────────────────────────────────

@admin.register(ResumeReview)
class ResumeReviewAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'overall_score', 'ats_score', 'version_number', 'created_at')
    list_filter = ('version_number', 'created_at')
    search_fields = ('user__email',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'


# ─── CoverLetter ──────────────────────────────────────────────────────────────

@admin.register(CoverLetter)
class CoverLetterAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'job_title', 'company_name', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__email', 'job_title', 'company_name')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'


# ─── LinkedInPost ─────────────────────────────────────────────────────────────

@admin.register(LinkedInPost)
class LinkedInPostAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'topic', 'tone', 'created_at')
    list_filter = ('tone', 'created_at')
    search_fields = ('user__email', 'topic')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'


# ─── InterviewSummaryVideo ────────────────────────────────────────────────────

@admin.register(InterviewSummaryVideo)
class InterviewSummaryVideoAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'assessment', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__email',)
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'


# ─── CareerIntake ─────────────────────────────────────────────────────────────

@admin.register(CareerIntake)
class CareerIntakeAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'target_role', 'timeline', 'updated_at')
    search_fields = ('user__email', 'target_role')
    readonly_fields = ('updated_at',)
    ordering = ('-updated_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'


# ─── PlacementDrive ───────────────────────────────────────────────────────────

@admin.register(PlacementDrive)
class PlacementDriveAdmin(admin.ModelAdmin):
    list_display = (
        'user_email',
        'current_stage',
        'final_outcome',
        'created_at',
        'completed_at',
    )
    list_filter = ('current_stage', 'final_outcome', 'created_at')
    search_fields = ('user__email',)
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'
