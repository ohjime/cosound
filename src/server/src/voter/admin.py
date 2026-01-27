from django.contrib import admin

from unfold.admin import ModelAdmin, TabularInline

from voter.models import Voter, Vote


class VoteInline(TabularInline):
    model = Vote
    extra = 0


@admin.register(Voter)
class VoterAdmin(ModelAdmin):
    list_display = ["user", "created_at"]
    inlines = [VoteInline]


@admin.register(Vote)
class VoteAdmin(ModelAdmin):
    list_display = ["voter", "player", "value", "created_at"]
