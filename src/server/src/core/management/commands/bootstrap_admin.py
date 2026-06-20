import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Idempotently create the first superuser from FIRST_ADMIN_* env vars."

    def handle(self, *args, **options):
        email = (os.environ.get("FIRST_ADMIN_EMAIL") or "").strip()
        username = (os.environ.get("FIRST_ADMIN_USERNAME") or "").strip()
        password = os.environ.get("FIRST_ADMIN_PASSWORD") or ""

        if not (email and username and password):
            self.stdout.write(
                "bootstrap_admin: FIRST_ADMIN_EMAIL/USERNAME/PASSWORD not all set; skipping."
            )
            return

        User = get_user_model()

        # Only ever bootstrap when the site has NO superuser at all. Once any
        # superuser exists, this is not a first run, so we never create or
        # promote — even if the admin's email was later changed or the default
        # admin account was deleted. This keeps deploys/builds idempotent and
        # stops the first superuser from being recreated every run.
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write("bootstrap_admin: a superuser already exists; skipping.")
            return

        # No superuser yet. If an account already uses this email (e.g. a plain
        # user), promote it rather than colliding on the unique constraint;
        # otherwise create the first superuser.
        user = User.objects.filter(email=email).first()
        if user is None:
            User.objects.create_superuser(
                email=email, username=username, password=password
            )
            self.stdout.write(
                self.style.SUCCESS(f"bootstrap_admin: created first superuser {email}")
            )
            return

        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=["is_superuser", "is_staff"])
        self.stdout.write(
            self.style.SUCCESS(
                f"bootstrap_admin: promoted existing user {email} to first superuser"
            )
        )
