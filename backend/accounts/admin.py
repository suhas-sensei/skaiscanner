from django.contrib import admin

from .models import EmailOTP


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at", "expires_at", "consumed_at", "attempts")
    list_filter = ("created_at", "expires_at", "consumed_at")
    search_fields = ("email",)
    readonly_fields = ("code_hash", "created_at", "consumed_at", "attempts")
