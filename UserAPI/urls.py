from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import payments_views

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    
    # Password Reset Flow
    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='auth/password_reset_form.html',
        email_template_name='auth/password_reset_email.html',
        success_url='/auth/password_reset/done/'
    ), name='password_reset'),
    
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='auth/password_reset_done.html'
    ), name='password_reset_done'),
    
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='auth/password_reset_confirm.html',
        success_url='/auth/reset/done/'
    ), name='password_reset_confirm'),
    
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='auth/password_reset_complete.html'
    ), name='password_reset_complete'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('individual-dashboard/', views.individual_dashboard_view, name='individual_dashboard'),
    path('join-institution/', views.join_institution, name='join_institution'),
    path('settings/', views.user_settings_view, name='user_settings'),
    # Feature #22 — Voice Interviewer
    path('voice-interviewer/personas/', views.get_personas_view, name='get_personas'),
    path('voice-interviewer/preference/', views.update_persona_preference, name='voice_interviewer_preference'),
    path('debug-urls/', views.debug_urls, name='debug_urls'),

    # ─── Payments (Razorpay) ──────────────────────────────────────────────
    path('payments/create-order/', payments_views.create_order, name='create_order'),
    path('payments/verify/', payments_views.verify_payment, name='verify_payment'),
    path('payments/', views.pricing_page_view, name='pricing_page'),

    # ─── Sales Inquiry (B2B) ───────────────────────────────────────────────
    path('sales/inquiry/', views.sales_inquiry, name='sales_inquiry'),
]