"""One-time data migration: turn the free-text Sound.artist into Artist rows.

For every sound that still has the legacy free-text artist but no Artist FK,
this creates (or reuses) an Artist with that name and links the sound to it.

Sounds are intentionally left with no Set — an ungrouped sound is treated as a
"single", which is the default going forward.

Idempotent: running it again only touches sounds that don't yet have an artist
FK, so it is safe to re-run.

Usage:
    uv run src/main.py convert_artists          # apply
    uv run src/main.py convert_artists --dry-run # report only
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Artist, Sound

UNKNOWN = "Unknown Artist"


class Command(BaseCommand):
    help = "Create Artist rows from each Sound's legacy free-text artist and link them."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Only sounds that haven't been converted yet.
        pending = Sound.objects.filter(artist__isnull=True)
        total = pending.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to convert — every sound already has an artist."))
            return

        # Build the unique set of names we need up front.
        names = set()
        for legacy in pending.values_list("artist_legacy", flat=True):
            names.add((legacy or "").strip() or UNKNOWN)

        self.stdout.write(
            f"{total} sound(s) to convert across {len(names)} distinct artist(s)."
        )

        if dry_run:
            for name in sorted(names):
                count = pending.filter(
                    artist_legacy=("" if name == UNKNOWN else name)
                ).count()
                self.stdout.write(f"  - {name}")
            self.stdout.write(self.style.WARNING("Dry run — no changes written."))
            return

        created_artists = 0
        linked_sounds = 0
        with transaction.atomic():
            # Map each name -> Artist, creating artists as needed.
            name_to_artist = {}
            for name in names:
                artist, created = Artist.objects.get_or_create(name=name)
                name_to_artist[name] = artist
                if created:
                    created_artists += 1

            # Link each sound, bypassing Sound.save() so we don't recompute embeddings.
            for sound in pending.only("id", "artist_legacy"):
                name = (sound.artist_legacy or "").strip() or UNKNOWN
                artist = name_to_artist[name]
                Sound.objects.filter(pk=sound.pk).update(artist=artist)
                linked_sounds += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {created_artists} artist(s), linked {linked_sounds} sound(s). "
                "All sounds left ungrouped (no set)."
            )
        )
