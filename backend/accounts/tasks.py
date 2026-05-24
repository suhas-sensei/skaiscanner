from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task
def send_email_otp(email, code):
    return send_mail(
        subject="Your Skaiscanner sign-in code",
        message=f"Your Skaiscanner sign-in code is {code}. It expires in {settings.EMAIL_OTP_EXPIRY_MINUTES} minutes.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
