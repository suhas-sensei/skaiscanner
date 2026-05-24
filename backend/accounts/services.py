import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .models import EmailOTP
from .tasks import send_email_otp


def normalize_email(email):
    return email.strip().lower()


def generate_otp_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def request_email_otp(email):
    email = normalize_email(email)
    code = generate_otp_code()
    expires_at = timezone.now() + timedelta(minutes=settings.EMAIL_OTP_EXPIRY_MINUTES)
    otp = EmailOTP.objects.create(
        email=email,
        code_hash=make_password(code),
        expires_at=expires_at,
    )
    send_email_otp.delay(email, code)
    return otp


def verify_email_otp(email, code):
    email = normalize_email(email)
    otp = (
        EmailOTP.objects.filter(email=email, consumed_at__isnull=True, expires_at__gt=timezone.now())
        .order_by("-created_at")
        .first()
    )
    if otp is None:
        return None

    otp.attempts += 1
    if otp.attempts > settings.EMAIL_OTP_MAX_ATTEMPTS:
        otp.consumed_at = timezone.now()
        otp.save(update_fields=["attempts", "consumed_at"])
        return None

    if not check_password(code, otp.code_hash):
        otp.save(update_fields=["attempts"])
        return None

    otp.consumed_at = timezone.now()
    otp.save(update_fields=["attempts", "consumed_at"])
    return get_or_create_user(email)


def get_or_create_user(email):
    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=email,
        defaults={
            "email": email,
        },
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    elif user.email != email:
        user.email = email
        user.save(update_fields=["email"])
    return user
