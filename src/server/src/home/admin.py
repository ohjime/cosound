from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Home, HomeLayer


@admin.register(Home)
class HomeAdmin(ModelAdmin):
    list_display = ("id", "user", "created_at", "updated_at")
    readonly_fields = ("created_at", "updated_at")


@admin.register(HomeLayer)
class HomeLayerAdmin(ModelAdmin):
    list_display = ("id", "home", "sound", "user", "gain", "created_at")
    readonly_fields = ("created_at",)
