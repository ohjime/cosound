from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Mix, MixLayer


@admin.register(Mix)
class MixAdmin(ModelAdmin):
    list_display = ("id", "user", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MixLayer)
class MixLayerAdmin(ModelAdmin):
    list_display = ("id", "mix", "sound", "user", "gain", "created_at")
    readonly_fields = ("created_at",)
