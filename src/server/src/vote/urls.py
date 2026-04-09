from django.urls import path
from django.views.generic import RedirectView

from vote.views import (
    voter_index,
    check_auth,
    check_email,
    check_code,
    cancel_code,
    logout_session,
    login_anonymously,
    submit_vote,
)


app_name = "vote"

urlpatterns = [
    # Voting Views
    path("", voter_index, name="vote"),
]

htmx_urlpatterns = [
    path("check_auth/", check_auth, name="check_auth"),
    path("check_email/", check_email, name="check_email"),
    path("check_code/", check_code, name="check_code"),
    path("cancel_code/", cancel_code, name="cancel_code"),
    path("logout_session/", logout_session, name="logout_session"),
    path("login_anonymously/", login_anonymously, name="login_anonymously"),
    path("submit_vote/", submit_vote, name="submit_vote"),
]

urlpatterns += htmx_urlpatterns
