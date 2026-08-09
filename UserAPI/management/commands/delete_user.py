from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = "Delete a specific user by email."

    def handle(self, *args, **options):
        User = get_user_model()

        email = "harshitgarg77.edu@gmail.com"

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(
                    f"No user found with email: {email}"
                )
            )
            return

        self.stdout.write(
            f"Deleting user: {user.email} ({user.username})"
        )

        user.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {email}"
            )
        )