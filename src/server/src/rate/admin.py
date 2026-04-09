from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import SoundRating


@admin.register(SoundRating)
class SoundRatingAdmin(ModelAdmin):
    list_display = ("user", "sound", "rating", "created_at", "updated_at")
    list_filter = ("rating",)
    readonly_fields = ("created_at", "updated_at")
