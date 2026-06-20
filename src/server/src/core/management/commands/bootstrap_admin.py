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
        user = User.objects.filter(email=email).first()

        if user is None:
            User.objects.create_superuser(
                email=email, username=username, password=password
            )
            self.stdout.write(self.style.SUCCESS(f"bootstrap_admin: created superuser {email}"))
            return

        # User already exists — ensure it is a superuser, but do NOT reset the
        # password (it may have been rotated since first deploy).
        changed = []
        if not user.is_superuser:
            user.is_superuser = True
            changed.append("is_superuser")
        if not user.is_staff:
            user.is_staff = True
            changed.append("is_staff")
        if changed:
            user.save(update_fields=changed)
            self.stdout.write(
                self.style.SUCCESS(
                    f"bootstrap_admin: promoted existing user {email} ({', '.join(changed)})"
                )
            )
        else:
            self.stdout.write(f"bootstrap_admin: superuser {email} already present; no change.")
