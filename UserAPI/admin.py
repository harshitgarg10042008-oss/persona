from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    CustomUser,
    IndividualUser,
    BusinessUser,
    Institution,
    InstitutionDomain,
    SubscriptionTier,
    PaymentTransaction,
    InstitutionMembership,
    UserInterviewerPreference,
    SalesInquiry,
)


# ─── CustomUser ───────────────────────────────────────────────────────────────

@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        'email',
        'username',
        'first_name',
        'institution',
        'is_active',
        'is_staff',
        'date_joined',
        'tier_display',
    )
    list_filter = ('institution', 'is_staff', 'is_active', 'date_joined')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    readonly_fields = ('date_joined', 'last_login')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'institution')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    def tier_display(self, obj):
        """Show the user's current subscription tier."""
        try:
            sub = obj.subscription
            if sub.is_premium:
                return 'Premium'
            return 'Free'
        except Exception:
            return 'No subscription'

    tier_display.short_description = 'Tier'


# ─── IndividualUser ───────────────────────────────────────────────────────────

@admin.register(IndividualUser)
class IndividualUserAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'user_email',
        'current_streak',
        'longest_streak',
        'last_activity_date',
        'created_at',
    )
    list_filter = ('last_activity_date', 'created_at')
    search_fields = ('name', 'user__email', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'


# ─── BusinessUser ─────────────────────────────────────────────────────────────

@admin.register(BusinessUser)
class BusinessUserAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'company_name',
        'user_email',
        'institution_code',
        'seat_cap_display',
        'member_count',
        'created_at',
    )
    list_filter = ('created_at',)
    search_fields = ('name', 'company_name', 'user__email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'Email'

    def member_count(self, obj):
        return obj.member_individuals.count()
    member_count.short_description = 'Members'

    def seat_cap_display(self, obj):
        return obj.seat_cap if obj.seat_cap is not None else '∞ Unlimited'
    seat_cap_display.short_description = 'Seat Cap'


# ─── Institution ──────────────────────────────────────────────────────────────


class InstitutionDomainInline(admin.TabularInline):
    """Manage allowed email domains directly from the Institution edit page."""
    model = InstitutionDomain
    extra = 1
    fields = ('domain', 'added_at')
    readonly_fields = ('added_at',)
    verbose_name = 'Allowed Email Domain'
    verbose_name_plural = 'Allowed Email Domains'

@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'code',
        'plan',
        'max_seats',
        'is_active',
        'created_at',
        'student_count',
        'domain_count',
    )
    list_filter = ('plan', 'is_active', 'created_at')
    search_fields = ('name', 'code', 'contact_email')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    actions = ['generate_new_code']
    inlines = [InstitutionDomainInline]

    def student_count(self, obj):
        return obj.students.count()
    student_count.short_description = 'Students'

    def domain_count(self, obj):
        return obj.allowed_domains.count()
    domain_count.short_description = 'Domains'

    @admin.action(description='Generate new code for selected institutions')
    def generate_new_code(self, request, queryset):
        for inst in queryset:
            inst.code = inst.generate_unique_code()
            inst.save()
        self.message_user(request, f"New codes generated for {queryset.count()} institutions.")


# ─── InstitutionDomain (also registered standalone for direct access) ─────────

@admin.register(InstitutionDomain)
class InstitutionDomainAdmin(admin.ModelAdmin):
    list_display = ('domain', 'institution', 'added_at')
    list_filter = ('institution',)
    search_fields = ('domain', 'institution__name')
    readonly_fields = ('added_at',)
    ordering = ('institution', 'domain')

# ─── SubscriptionTier ─────────────────────────────────────────────────────────

@admin.register(SubscriptionTier)
class SubscriptionTierAdmin(admin.ModelAdmin):
    list_display = (
        'user_email',
        'tier',
        'is_premium',
        'is_active',
        'institution',
        'premium_expires_at',
        'created_at',
        'updated_at',
    )
    list_filter = ('tier', 'is_active', 'institution', 'created_at')
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'

    def is_premium(self, obj):
        return obj.is_premium
    is_premium.boolean = True
    is_premium.short_description = 'Premium'


# ─── PaymentTransaction ───────────────────────────────────────────────────────

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'user_email',
        'plan',
        'amount_display',
        'status',
        'razorpay_order_id',
        'razorpay_payment_id',
        'created_at',
        'verified_at',
    )
    list_filter = ('plan', 'status', 'created_at')
    search_fields = (
        'user__email',
        'user__username',
        'razorpay_order_id',
        'razorpay_payment_id',
    )
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'

    def amount_display(self, obj):
        """Display amount in INR (stored in paise)."""
        return f"₹{obj.amount / 100:.2f}"
    amount_display.short_description = 'Amount (INR)'


# ─── InstitutionMembership ───────────────────────────────────────────────────

@admin.register(InstitutionMembership)
class InstitutionMembershipAdmin(admin.ModelAdmin):
    list_display = (
        'individual_name',
        'business_name',
        'consent_granted',
        'is_active',
        'joined_at',
    )
    list_filter = ('consent_granted', 'is_active', 'joined_at')
    search_fields = (
        'individual__name',
        'business__company_name',
        'business__name',
    )
    readonly_fields = ('joined_at',)
    ordering = ('-joined_at',)

    def individual_name(self, obj):
        return obj.individual.name
    individual_name.short_description = 'Individual'

    def business_name(self, obj):
        return obj.business.company_name or obj.business.name
    business_name.short_description = 'Institution'


# ─── UserInterviewerPreference ───────────────────────────────────────────────

@admin.register(UserInterviewerPreference)
class UserInterviewerPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'persona_id', 'updated_at')
    list_filter = ('persona_id',)
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('updated_at',)
    ordering = ('-updated_at',)

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User Email'


# ─── SalesInquiry (Leads) ────────────────────────────────────────────────────

@admin.register(SalesInquiry)
class SalesInquiryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'email',
        'institution_name',
        'plan_interest',
        'status',
        'phone',
        'created_at',
    )
    list_filter = ('plan_interest', 'status', 'created_at')
    search_fields = ('name', 'email', 'institution_name', 'phone')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
    list_editable = ('status',)
