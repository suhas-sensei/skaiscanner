from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Send a test email using the configured Django email backend."

    def add_arguments(self, parser):
        parser.add_argument("recipient")

    def handle(self, *args, **options):
        recipient = options["recipient"]
        sent = send_mail(
            subject="Skaiscanner email test",
            message="Your Skaiscanner email backend is configured correctly.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} test email to {recipient}"))
