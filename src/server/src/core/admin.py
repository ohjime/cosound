from import_export.admin import ImportExportModelAdmin
from import_export import resources, widgets, fields
from unfold.contrib.import_export.forms import ExportForm, ImportForm
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

from core.models import Manager, User, Sound, Player, Listener
from core.forms import SoundForm


class ListenerInline(StackedInline):
    model = Listener


class ManagerInline(StackedInline):
    model = Manager


class PlayerInline(TabularInline):
    model = Player
    extra = 0


model = django_apps.get_model("django_file_form", "TemporaryUploadedFile")
admin.site.unregister(model)

admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    inlines = [ManagerInline, ListenerInline]

    class Meta:
        model = User
        verbose_name = "Users"

    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_filter_submit = True
    list_filter = [("email", FieldTextFilter)]


class VectorWidget(widgets.Widget):
    def clean(self, value, row=None, **kwargs):
        if not value:
            return None
        if isinstance(value, list):
            return value
        s = str(value).strip().strip("[]")
        return [float(x) for x in s.split()]

    def render(self, value, obj=None, **kwargs):
        if value is None:
            return ""
        return str(value)


class SoundResource(resources.ModelResource):
    embeddings = fields.Field(
        column_name="embeddings",
        attribute="embeddings",
        widget=VectorWidget(),
    )

    class Meta:
        model = Sound
        import_id_fields = ["id"]


@admin.register(Sound)
class SoundAdmin(FileFormAdmin, ModelAdmin, ImportExportModelAdmin):  # type: ignore
    form = SoundForm
    resource_classes = [SoundResource]

    # Add Unfold's styled forms for the import/export pages
    import_form_class = ImportForm
    export_form_class = ExportForm

    list_display = ["title", "artist", "type", "created_at", "updated_at"]


@admin.register(Player)
class PlayerAdmin(ModelAdmin):
    list_display = ["name", "account"]
    exclude = ["playing", "token"]
    list_filter = [("name", FieldTextFilter)]


@admin.register(Manager)
class ManagerAdmin(ModelAdmin):
    list_display = ["name", "user", "created_at"]
    list_filter = [("name", FieldTextFilter)]
    inlines = [PlayerInline]


@admin.register(Listener)
class ListenerAdmin(ModelAdmin):
    list_display = ["user", "created_at"]
