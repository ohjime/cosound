import uuid
import random
from allauth.account.adapter import DefaultAccountAdapter
from django import forms
from voter.models import Voter

from core.models import User


class UnifiedLoginAdapter(DefaultAccountAdapter):
    """Custom adapter for unified login flow."""

    def generate_login_code(self):
        """Simple numeric code generator."""
        return "".join(random.choices("0123456789", k=6))

    def is_open_for_signup(self, request):
        return True


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

    def clean_email(self):
        email = self.cleaned_data.get("email", "").lower().strip()

        # Get or Create User (case-insensitive)
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            user = User.objects.create(
                email=email,
                username=f"{email.split('@')[0]}_{uuid.uuid4().hex[:8]}",
            )
            user.set_unusable_password()
            user.save()

        # Ensure Voter Profile exists
        if not hasattr(user, "voter"):
            Voter.objects.create(user=user)

        return email
