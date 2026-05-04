from django.contrib import admin
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.safestring import mark_safe

from unfold.admin import ModelAdmin, TabularInline

from core.models import Listener, Player
from core.admin import (
    ListenerAdmin as CoreListenerAdmin,
    PlayerAdmin as CorePlayerAdmin,
)
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
    fieldsets = list(CorePlayerAdmin.fieldsets) + [
        (
            "Player Utilities",
            {"fields": ["token_display", "vote_urls"]},
        ),
    ]

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

    vote_urls.short_description = "NFC URLs"  # type: ignore


admin.site.unregister(Listener)


@admin.register(Listener)
class ListenerAdmin(CoreListenerAdmin):
    readonly_fields = tuple(getattr(CoreListenerAdmin, "readonly_fields", ())) + (
        "votes_display",
    )
    fieldsets = list(CoreListenerAdmin.fieldsets) + [
        (
            "Votes",
            {"classes": ["tab"], "fields": ["votes_display"]},
        ),
    ]

    @admin.display(description="Votes")
    def votes_display(self, obj):
        votes = (
            list(obj.vote_set.select_related("player").order_by("-created_at"))
            if obj
            else []
        )
        if not votes:
            return mark_safe(
                '<div class="text-sm text-font-subtle-light dark:text-font-subtle-dark">'
                "No votes"
                "</div>"
            )
        rows = []
        for v in votes:
            url = reverse("admin:vote_vote_change", args=[v.pk])
            color = "text-green-600" if v.value > 0 else "text-red-600"
            arrow = "▲" if v.value > 0 else "▼"
            ts = v.created_at.strftime("%Y-%m-%d %H:%M")
            rows.append(
                f'<li class="py-2 border-b border-base-200 dark:border-base-800 last:border-0 flex items-center gap-3">'
                f'<span class="{color} font-bold">{arrow}</span>'
                f'<a href="{url}" class="font-medium text-font-default-light dark:text-font-default-dark hover:underline">{v.player}</a>'
                f'<span class="text-xs text-font-subtle-light dark:text-font-subtle-dark ml-auto">{ts}</span>'
                f"</li>"
            )
        return mark_safe(
            '<ul class="rounded-default border border-base-200 dark:border-base-800 px-4 bg-white dark:bg-base-900 list-none m-0">'
            + "".join(rows)
            + "</ul>"
        )
