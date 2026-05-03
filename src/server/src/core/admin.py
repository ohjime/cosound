import secrets

from import_export.admin import ImportExportModelAdmin
from import_export import resources, widgets, fields
from unfold.contrib.import_export.forms import ExportForm, ImportForm
import json
from django.contrib import admin, messages
from django.apps import apps as django_apps
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils.safestring import mark_safe
from django.template.loader import render_to_string
from django_file_form.model_admin import FileFormAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin, TabularInline, StackedInline
from unfold.contrib.filters.admin import FieldTextFilter
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from core.models import Manager, User, Sound, Player, Listener, Cosound
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


class TaggitWidget(widgets.Widget):
    def render(self, value, obj=None, **kwargs):
        if not value:
            return ""
        if hasattr(value, "names"):
            return ", ".join(value.names())
        if isinstance(value, (list, tuple)):
            return ", ".join(str(v) for v in value)
        return str(value)

    def clean(self, value, row=None, **kwargs):
        if not value:
            return []
        return [tag.strip() for tag in value.split(",") if tag.strip()]


class TagsField(fields.Field):
    def save(self, instance, row, is_m2m=False, **kwargs):
        # Tag assignment is deferred to SoundResource.after_save_instance
        # because TaggableManager doesn't support setattr and requires a saved pk.
        return


class SoundResource(resources.ModelResource):
    embeddings = fields.Field(
        column_name="embeddings",
        attribute="embeddings",
        widget=VectorWidget(),
    )
    tags = TagsField(
        column_name="tags",
        attribute="tags",
        widget=TaggitWidget(),
    )

    class Meta:
        model = Sound
        import_id_fields = ["id"]
        fields = (
            "id",
            "title",
            "artist",
            "tags",
            "embeddings",
            "flavor",
            "file",
            "art",
        )

    def after_save_instance(self, instance, row, **kwargs):
        raw = row.get("tags") if hasattr(row, "get") else None
        if raw is None:
            return
        if isinstance(raw, (list, tuple)):
            tag_list = [str(t).strip() for t in raw if str(t).strip()]
        else:
            tag_list = [t.strip() for t in str(raw).split(",") if t.strip()]
        if tag_list:
            instance.tags.set(tag_list, clear=True)
        else:
            instance.tags.clear()


@admin.register(Sound)
class SoundAdmin(FileFormAdmin, ModelAdmin, ImportExportModelAdmin):  # type: ignore
    form = SoundForm
    resource_classes = [SoundResource]

    # Add Unfold's styled forms for the import/export pages
    import_form_class = ImportForm
    export_form_class = ExportForm

    list_display = ["title", "artist", "created_at", "updated_at"]
    compressed_fields = True
    fieldsets = [
        (
            None,
            {
                "fields": [
                    "title",
                    "artist",
                    "art",
                    "file",
                ],
            },
        ),
        (
            "Details",
            {
                "fields": [
                    "flavor",
                    "tags",
                ],
            },
        ),
    ]


@admin.register(Player)
class PlayerAdmin(ModelAdmin):
    list_display = ["name", "manager"]
    list_filter = [("name", FieldTextFilter)]
    filter_horizontal = ["sounds"]
    readonly_fields = ["playing_display", "token_display"]
    compressed_fields = True
    fieldsets = [
        (
            "Player Info",
            {
                "fields": [
                    "name",
                    "photo",
                    "bio",
                    "manager",
                    "location",
                    "token_display",
                ],
            },
        ),
        (
            "Sound Library",
            {
                "fields": [
                    "sounds",
                    "playing_display",
                ],
            },
        ),
    ]

    def get_form(self, request, obj=None, change=False, **kwargs):
        self._current_request = request
        return super().get_form(request, obj, change, **kwargs)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/regenerate-token/",
                self.admin_site.admin_view(self.regenerate_token_view),
                name="core_player_regenerate_token",
            ),
        ]
        return custom + urls

    def regenerate_token_view(self, request, object_id):
        player = self.get_object(request, object_id)
        if player is None:
            messages.error(request, "Player not found.")
            return HttpResponseRedirect(reverse("admin:core_player_changelist"))
        player.token = secrets.token_hex(32)
        player.save(update_fields=["token"])
        messages.success(request, "Token regenerated.")
        return HttpResponseRedirect(
            reverse("admin:core_player_change", args=[player.pk])
        )

    @admin.display(description="Token")
    def token_display(self, obj):
        if not obj or not obj.token:
            return mark_safe(
                '<div class="text-sm text-font-subtle-light dark:text-font-subtle-dark">—</div>'
            )
        token = obj.token
        refresh_url = reverse("admin:core_player_regenerate_token", args=[obj.pk])
        return mark_safe(f"""
            <div class="flex flex-col gap-2 w-full">
              <input type="text" readonly value="{token}"
                class="font-mono text-xs bg-base-50 dark:bg-base-900 border border-base-200 dark:border-base-800 rounded-default px-2 py-1 w-full min-w-0 text-ellipsis overflow-hidden whitespace-nowrap"
                onclick="this.select()" />
              <div>
                <button type="button"
                  style="display:inline-block;padding:8px 16px;margin-right:8px;border-radius:6px;color:#fff;font-weight:600;border:none;cursor:pointer;background:#2563eb;"
                  onclick="navigator.clipboard.writeText('{token}').then(() => {{ this.innerText='✓ Copied'; setTimeout(() => this.innerText='📋 Copy Token', 1500); }})">
                  📋 Copy Token
                </button>
                <button type="button"
                  style="display:inline-block;padding:8px 16px;margin-right:8px;border-radius:6px;color:#fff;font-weight:600;border:none;cursor:pointer;background:#dc2626;"
                  onclick="
                    if (!confirm('Regenerate token? The old token will stop working.')) return;
                    const csrftoken = document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1];
                    fetch('{refresh_url}', {{
                      method: 'POST',
                      headers: {{ 'X-CSRFToken': csrftoken }},
                      credentials: 'same-origin',
                    }}).then(r => {{
                      if (r.ok || r.redirected) location.reload();
                      else alert('Failed to refresh token');
                    }});">
                  ↻ Refresh Token
                </button>
              </div>
            </div>
            """)

    @admin.display(description="Now playing")
    def playing_display(self, obj):
        playing = obj.playing
        layers = []
        if playing is not None:
            data = playing.model_dump() if hasattr(playing, "model_dump") else playing
            layers = (data or {}).get("layers", []) or []

        if not layers:
            return mark_safe(
                '<div class="text-sm text-font-subtle-light dark:text-font-subtle-dark">'
                "Nothing playing"
                "</div>"
            )

        sound_ids = [l.get("sound_id") for l in layers if l.get("sound_id") is not None]
        sounds = {s.pk: s for s in Sound.objects.filter(pk__in=sound_ids)}

        rows = []
        for layer in layers:
            sid = layer.get("sound_id")
            gain = float(layer.get("sound_gain", 0) or 0)
            pct = max(0, min(100, round(gain * 100)))
            sound = sounds.get(sid)
            title = sound.title if sound else "(missing sound)"
            artist = sound.artist if sound else ""
            meta = f"{artist} &middot; #{sid}" if artist else f"#{sid}"
            rows.append(f"""
                <div class="flex items-center gap-3 py-2 border-b border-base-200 dark:border-base-800 last:border-0">
                  <div class="flex-1 min-w-0">
                    <div class="font-medium text-font-default-light dark:text-font-default-dark truncate">{title}</div>
                    <div class="text-xs text-font-subtle-light dark:text-font-subtle-dark truncate">{meta}</div>
                  </div>
                  <div class="w-40 shrink-0">
                    <div class="h-2 rounded-full bg-base-200 dark:bg-base-800 overflow-hidden">
                      <div class="h-full bg-primary-600 dark:bg-primary-500" style="width: {pct}%"></div>
                    </div>
                  </div>
                  <div class="w-12 text-right tabular-nums text-xs text-font-default-light dark:text-font-default-dark">{gain:.2f}</div>
                </div>
                """)
        return mark_safe(
            '<div class="rounded-default border border-base-200 dark:border-base-800 px-4 py-2 bg-white dark:bg-base-900">'
            + "".join(rows)
            + "</div>"
        )


@admin.register(Manager)
class ManagerAdmin(ModelAdmin):
    list_display = ["name", "user", "created_at"]
    list_filter = [("name", FieldTextFilter)]
    inlines = [PlayerInline]


@admin.register(Listener)
class ListenerAdmin(ModelAdmin):
    list_display = ["user", "created_at"]
    readonly_fields = ["collection_display", "created_at", "updated_at"]
    compressed_fields = True
    fieldsets = [
        (
            None,
            {"fields": ["user", "created_at", "updated_at"]},
        ),
        (
            "Collection",
            {"classes": ["tab"], "fields": ["collection_display"]},
        ),
    ]

    @admin.display(description="Saved sounds")
    def collection_display(self, obj):
        sounds = list(obj.collection.all().order_by("title")) if obj else []
        if not sounds:
            return mark_safe(
                '<div class="text-sm text-font-subtle-light dark:text-font-subtle-dark">'
                "Empty collection"
                "</div>"
            )
        rows = []
        for s in sounds:
            url = reverse("admin:core_sound_change", args=[s.pk])
            rows.append(
                f'<li class="py-2 border-b border-base-200 dark:border-base-800 last:border-0">'
                f'<a href="{url}" class="font-medium text-font-default-light dark:text-font-default-dark hover:underline">{s.title}</a>'
                f'<span class="text-xs text-font-subtle-light dark:text-font-subtle-dark"> &middot; {s.artist} &middot; #{s.pk}</span>'
                f"</li>"
            )
        return mark_safe(
            '<ul class="rounded-default border border-base-200 dark:border-base-800 px-4 bg-white dark:bg-base-900 list-none m-0">'
            + "".join(rows)
            + "</ul>"
        )


@admin.register(Cosound)
class CosoundAdmin(ModelAdmin):
    list_display = ["created_at"]
