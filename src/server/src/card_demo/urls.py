from django.urls import path

from card_demo.views import card_demo


app_name = "card_demo"

urlpatterns = [
    path("", card_demo, name="index"),
]
