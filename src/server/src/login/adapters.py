import uuid
import random
from allauth.account.adapter import DefaultAccountAdapter
from django import forms

from core.models import User, Listener
from core.tasks import send_auth_email_task
from login.utils import generate_anon_username


class UnifiedLoginAdapter(DefaultAccountAdapter):
    """Custom adapter for unified login flow."""

    def generate_login_code(self):
        """Simple numeric code generator."""
        return "".join(random.choices("0123456789", k=6))

    def is_open_for_signup(self, request):
        return True

    def send_mail(self, template_prefix, email, context):
        msg = self.render_mail(template_prefix, email, context)

        # Extract HTML if present
        html_content = msg.alternatives[0][0] if msg.alternatives else None

        # Enqueue the background task
        send_auth_email_task.enqueue(
            subject=msg.subject,
            body=msg.body,
            to_email=email,
            html_content=html_content,
        )


class UnifiedRequestLoginCodeForm(forms.Form):
    """
    Validates email input and ensures a User account exists (Auto-Signup).
    """

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(
            attrs={"placeholder": "Enter your email", "autofocus": True}
        ),
    )

    @staticmethod
    def _generate_unique_username():
        for _ in range(10):
            username = generate_anon_username()
            if not User.objects.filter(username__iexact=username).exists():
                return username
        return f"user_{uuid.uuid4().hex[:12]}"

    def clean_email(self):
        email = self.cleaned_data.get("email", "").lower().strip()

        # Get or Create User (case-insensitive)
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            user = User.objects.create(
                email=email,
                username=self._generate_unique_username(),
            )
            user.set_unusable_password()
            user.save()

        # Ensure Listener Profile exists
        if not hasattr(user, "listener"):
            Listener.objects.create(user=user)

        return email
