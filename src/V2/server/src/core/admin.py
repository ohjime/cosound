import json
from django.contrib import admin
from django.apps import apps as django_apps
from django.utils.safestring import mark_safe
from django.template.loader import render_to_string
from django_file_form.model_admin import FileFormAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from unfold.admin import ModelAdmin, TabularInline, StackedInline
from unfold.contrib.filters.admin import FieldTextFilter
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from core.models import PlayerAccount, User, Sound, Player
from core.forms import SoundForm
from voter.models import Voter


class VoterInline(StackedInline):
    model = Voter


class PlayerAccountInline(StackedInline):
    model = PlayerAccount


class PlayerInline(TabularInline):
    model = Player
    extra = 0


model = django_apps.get_model("django_file_form", "TemporaryUploadedFile")
admin.site.unregister(model)

admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    inlines = [PlayerAccountInline, VoterInline]

    class Meta:
        model = User
        verbose_name = "Users"

    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_filter_submit = True
    list_filter = [("email", FieldTextFilter)]


@admin.register(Sound)
class SoundAdmin(FileFormAdmin, ModelAdmin):  # type: ignore
    form = SoundForm

    list_display = ["title", "artist", "type", "created_at", "updated_at"]


@admin.register(Player)
class PlayerAdmin(ModelAdmin):
    list_display = ["name", "account"]
    readonly_fields = ["token"]
    list_filter = [("name", FieldTextFilter)]


@admin.register(PlayerAccount)
class PlayerAccountAdmin(ModelAdmin):
    list_display = ["name", "manager", "created_at"]
    list_filter = [("name", FieldTextFilter)]
    inlines = [PlayerInline]
