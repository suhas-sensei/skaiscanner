from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from .models import EmailOTP


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class EmailOTPAuthTests(TestCase):
    def graphql(self, query, variables=None):
        return self.client.post(
            "/graphql/",
            data={"query": query, "variables": variables or {}},
            content_type="application/json",
        )

    def test_request_email_otp_sends_code(self):
        response = self.graphql(
            """
            mutation RequestEmailOTP($email: String!) {
              requestEmailOtp(email: $email) {
                ok
                expiresAt
              }
            }
            """,
            {"email": "USER@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["requestEmailOtp"]["ok"])
        self.assertEqual(EmailOTP.objects.get().email, "user@example.com")
        self.assertEqual(len(mail.outbox), 1)

    def test_verify_email_otp_logs_user_in(self):
        self.graphql(
            """
            mutation RequestEmailOTP($email: String!) {
              requestEmailOtp(email: $email) { ok }
            }
            """,
            {"email": "user@example.com"},
        )
        code = mail.outbox[0].body.split(" is ")[1].split(".")[0]

        response = self.graphql(
            """
            mutation VerifyEmailOTP($email: String!, $code: String!) {
              verifyEmailOtp(email: $email, code: $code) {
                ok
                user { email username }
              }
            }
            """,
            {"email": "user@example.com", "code": code},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]["verifyEmailOtp"]
        self.assertTrue(data["ok"])
        self.assertEqual(data["user"]["email"], "user@example.com")
        self.assertTrue(get_user_model().objects.filter(username="user@example.com").exists())

        viewer_response = self.graphql("{ viewer { email } }")
        self.assertEqual(viewer_response.json()["data"]["viewer"]["email"], "user@example.com")

    def test_verify_email_otp_rejects_bad_code(self):
        self.graphql(
            """
            mutation RequestEmailOTP($email: String!) {
              requestEmailOtp(email: $email) { ok }
            }
            """,
            {"email": "user@example.com"},
        )

        response = self.graphql(
            """
            mutation VerifyEmailOTP($email: String!, $code: String!) {
              verifyEmailOtp(email: $email, code: $code) {
                ok
                user { email }
              }
            }
            """,
            {"email": "user@example.com", "code": "000000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["verifyEmailOtp"]["ok"])
        self.assertIsNone(response.json()["data"]["verifyEmailOtp"]["user"])

    def test_send_test_email_command_uses_configured_backend(self):
        call_command("send_test_email", "user@example.com")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["user@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Skaiscanner email test")
