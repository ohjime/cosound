"""Bulk-import Sound rows from local .mp3 files.

Title and artist are derived entirely from the filename — no xlsx lookup.
Any digit-bearing token is treated as an ID and dropped. Artists that are
a single-word handle, contain an email, or contain digits become
"Unknown Artist".

Usage (from the repo root):

    uv run src/server/src/main.py import_sounds
    uv run src/server/src/main.py import_sounds --dry-run
    uv run src/server/src/main.py import_sounds --update
"""

import re
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from core.models import Sound, SoundType


GMULYK_PREFIX = re.compile(r"^gmulyk-edit__")
LENGTH_SUFFIX = re.compile(r"__(?:3m|5mloop)$")

# Short words that stay lowercase when they appear inside a title. The first
# word of a title is always capitalized regardless.
TITLE_STOPWORDS = frozenset(
    {
        "a", "an", "and", "as", "at", "but", "by", "for", "from",
        "in", "into", "nor", "of", "on", "onto", "or", "so",
        "that", "the", "this", "to", "up", "with",
    }
)

# Spelled-out ordinals used to disambiguate titles that collide within the
# same import batch (e.g. two files that both map to "Pine Forest in the Wind"
# become "Pine Forest in the Wind Pt. One" and "Pt. Two").
PART_WORDS = [
    "One", "Two", "Three", "Four", "Five",
    "Six", "Seven", "Eight", "Nine", "Ten",
]


def _smart_title_case(text: str) -> str:
    """Title-case `text`, leaving stopwords lowercase (except as the first word).

    Single uppercase letters in the source (``Field A``, ``Take B``) are
    preserved as labels rather than treated as the article ``a``.
    """
    words = text.split()
    out: list[str] = []
    for i, w in enumerate(words):
        if len(w) == 1 and w.isalpha() and w.isupper():
            out.append(w)
            continue
        wl = w.lower()
        if i > 0 and wl in TITLE_STOPWORDS:
            out.append(wl)
        else:
            out.append(wl[:1].upper() + wl[1:])
    return " ".join(out)


def _has_digit(token: str) -> bool:
    return any(c.isdigit() for c in token)


def _format_title(raw: str) -> str:
    """Split `raw` on `-`/`_`/space, drop any token that contains a digit, title-case the rest."""
    tokens = [t for t in re.split(r"[-_\s]+", raw) if t and not _has_digit(t)]
    if not tokens:
        return "Untitled"
    return _smart_title_case(" ".join(tokens))


def _format_artist(raw: str) -> str:
    """Return a real-name-looking artist, or "Unknown Artist" when the token
    looks like a username, email, or ID."""
    raw = (raw or "").strip()
    if not raw or "@" in raw or _has_digit(raw):
        return "Unknown Artist"
    words = [w for w in re.split(r"[-_\s]+", raw) if w]
    # Require 2+ alphabetic words so that "Kay-Westhues" becomes a name but
    # "nikitralala" or "nfsgit" fall through to Unknown Artist.
    if len(words) < 2:
        return "Unknown Artist"
    if not all(re.fullmatch(r"[A-Za-z][A-Za-z']*", w) for w in words):
        return "Unknown Artist"
    return _smart_title_case(" ".join(words))


def _base_name(filename: str) -> str:
    stem = Path(filename).stem
    stem = GMULYK_PREFIX.sub("", stem)
    stem = LENGTH_SUFFIX.sub("", stem)
    return stem


def parse_filename(base: str) -> tuple[str, str]:
    """Return ``(title, artist)`` parsed from a gmulyk-style base name.

    Patterns supported::

        {id}__{author}__{title...}     # e.g. 121965__nfsgit__forest-birds-…
        {author}__{title...}           # e.g. Kay-Westhues__Woods-behind-…

    Any leading segments that contain a digit are skipped when looking for the
    author token, so ``ear0-33744__vox__birds-on-prairies`` resolves to
    ``author=vox, title=birds-on-prairies``.
    """
    parts = base.split("__")
    author_idx: int | None = None
    for i, p in enumerate(parts):
        if not _has_digit(p):
            author_idx = i
            break
    if author_idx is None or author_idx >= len(parts) - 1:
        return _format_title(base), "Unknown Artist"
    artist_raw = parts[author_idx]
    title_raw = "__".join(parts[author_idx + 1 :])
    return _format_title(title_raw), _format_artist(artist_raw)


class Command(BaseCommand):
    help = "Bulk-import Sound rows from local mp3 files in build/sounds/Looping Stems."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sounds-dir",
            default="build/sounds/Looping Stems",
            help="Folder of .mp3 files to import (default: build/sounds/Looping Stems)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the import plan without creating Sound rows or uploading files",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="If a Sound with the same title exists, update artist/file instead of skipping",
        )

    def handle(self, *args, **options):
        sounds_dir = Path(options["sounds_dir"]).expanduser()
        dry_run: bool = options["dry_run"]
        update: bool = options["update"]

        if not sounds_dir.is_dir():
            raise CommandError(f"Sounds directory not found: {sounds_dir}")

        mp3s = sorted(p for p in sounds_dir.iterdir() if p.suffix.lower() == ".mp3")
        self.stdout.write(f"Found {len(mp3s)} .mp3 files in {sounds_dir}")
        if not mp3s:
            return

        # Pass 1: parse every filename so we can detect in-batch title collisions
        # before we start writing. For groups where 2+ files collapse to the same
        # title (e.g. "Rain and Thunder in Moscow" from moscow-1 and moscow-2) we
        # disambiguate by appending " Pt. One", " Pt. Two", etc.
        parsed: list[tuple[Path, str, str]] = []
        title_counts: dict[str, int] = {}
        for mp3 in mp3s:
            title, artist = parse_filename(_base_name(mp3.name))
            parsed.append((mp3, title, artist))
            title_counts[title] = title_counts.get(title, 0) + 1

        seen: dict[str, int] = {}
        planned: list[tuple[Path, str, str]] = []
        for mp3, title, artist in parsed:
            if title_counts[title] > 1:
                idx = seen.get(title, 0)
                seen[title] = idx + 1
                suffix = PART_WORDS[idx] if idx < len(PART_WORDS) else str(idx + 1)
                title = f"{title} Pt. {suffix}"
            planned.append((mp3, title, artist))

        stats = {"created": 0, "updated": 0, "skipped": 0, "errored": 0}

        for mp3, title, artist in planned:
            existing = Sound.objects.filter(title=title).first()
            if existing and not update:
                action = "skip"
            elif existing:
                action = "update"
            else:
                action = "create"

            self.stdout.write(
                f"{action:6} title={title!r} artist={artist!r} file={mp3.name}"
            )

            if action == "skip":
                stats["skipped"] += 1
                continue
            if dry_run:
                stats[{"create": "created", "update": "updated"}[action]] += 1
                continue

            try:
                if action == "create":
                    sound = Sound(title=title, artist=artist, type=SoundType.SOUNDSCAPE)
                else:
                    sound = existing
                    sound.artist = artist

                with mp3.open("rb") as fh:
                    sound.file.save(mp3.name, File(fh), save=False)
                sound.save()
                stats[{"create": "created", "update": "updated"}[action]] += 1
            except Exception as exc:  # noqa: BLE001 — report & continue
                stats["errored"] += 1
                self.stderr.write(self.style.ERROR(f"  failed on {mp3.name}: {exc}"))

        self.stdout.write(self.style.SUCCESS("\n=== Import summary ==="))
        for k, v in stats.items():
            self.stdout.write(f"  {k}: {v}")
        if dry_run:
            self.stdout.write(self.style.WARNING("(dry-run — no changes written)"))
