from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, IndividualUser, BusinessUser, SalesInquiry

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'username', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active', 'date_joined')
    search_fields = ('email', 'username')
    ordering = ('email',)
    
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ()}),
    )

@admin.register(IndividualUser)
class IndividualUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'user__email', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    
    def user__email(self, obj):
        return obj.user.email
    user__email.short_description = 'Email'

@admin.register(BusinessUser)
class BusinessUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'company_name', 'user__email', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'company_name', 'user__email')
    readonly_fields = ('created_at', 'updated_at')

    def user__email(self, obj):
        return obj.user.email
    user__email.short_description = 'Email'


@admin.register(SalesInquiry)
class SalesInquiryAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'institution_name', 'plan_interest', 'status', 'created_at')
    list_filter = ('plan_interest', 'status', 'created_at')
    search_fields = ('name', 'email', 'institution_name')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
