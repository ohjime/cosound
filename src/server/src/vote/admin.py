from django.contrib import admin
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe

from unfold.admin import ModelAdmin, TabularInline

from core.models import Player
from core.admin import PlayerAdmin as CorePlayerAdmin
from vote.models import Vote


class VoteInline(TabularInline):
    model = Vote
    extra = 0


@admin.register(Vote)
class VoteAdmin(ModelAdmin):
    list_display = ["voter", "player", "value", "created_at"]


admin.site.unregister(Player)


@admin.register(Player)
class PlayerAdmin(CorePlayerAdmin):
    readonly_fields = tuple(getattr(CorePlayerAdmin, "readonly_fields", ())) + (
        "vote_urls",
    )

    def vote_urls(self, obj):
        if not obj or not obj.token:
            return "—"
        request = getattr(self, "_current_request", None)
        base = (
            request.build_absolute_uri(reverse("vote:vote"))
            if request
            else reverse("vote:vote")
        )
        return mark_safe(
            render_to_string(
                "admin/vote_urls.html",
                {"base_url": base, "player_token": obj.token},
            )
        )

    def get_form(self, request, obj=None, change=False, **kwargs):
        self._current_request = request
        return super().get_form(request, obj, change, **kwargs)

    vote_urls.short_description = "NFC URLs"
