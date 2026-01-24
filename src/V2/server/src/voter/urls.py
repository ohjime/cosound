from django.urls import path
from django.views.generic import RedirectView
from allauth.account import views as account_views
from voter.views import (
    guest_login_view,
    htmx_auth_options,
    htmx_login_email,
    htmx_login_code,
    voting_view,
)


urlpatterns = [
    # Voting Views
    path(
        "vote/",
        voting_view,
        name="vote",
    ),
    # HTMX Auth Modal Views
    path(
        "htmx/auth/options/",
        htmx_auth_options,
        name="htmx_auth_options",
    ),
    path(
        "htmx/login/email/",
        htmx_login_email,
        name="htmx_login_email",
    ),
    path(
        "htmx/login/code/",
        htmx_login_code,
        name="htmx_login_code",
    ),
    # Standard Auth Routes
    path(
        "login/",
        account_views.request_login_code,
        name="account_request_login_code",
    ),
    path(
        "verify/",
        account_views.confirm_login_code,
        name="account_confirm_login_code",
    ),
    path(
        "logout/",
        account_views.logout,
        name="account_logout",
    ),
    path(
        "signup/",
        RedirectView.as_view(pattern_name="account_request_login_code"),
        name="account_signup",
    ),
    path(
        "signin/",
        RedirectView.as_view(pattern_name="account_request_login_code"),
        name="account_login",
    ),
    path(
        "guest/login/",
        guest_login_view,
        name="account_guest_login",
    ),
]
