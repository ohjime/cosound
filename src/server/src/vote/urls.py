from django.urls import path

from vote.views import submit_vote, vote_initial, voter_index

app_name = "vote"

urlpatterns = [
    path("", voter_index, name="vote"),
    path("initial/", vote_initial, name="vote_initial"),
    path("submit_vote/", submit_vote, name="submit_vote"),
]
