import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / "env" / ".env")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import json
import pygame

MANIFEST_PATH = Path(__file__).parent.parent.parent / "manifest.json"

pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
pygame.mixer.set_num_channels(16)


class LayerManager:

    def __init__(self):
        self.active_channels = []
        self.instrumental_channel = None

    def transition(self, soundscapes, instrumental):
        with open(MANIFEST_PATH, "r") as f:
            manifest = json.load(f)
        for ch in self.active_channels:
            ch.fadeout(6000)
        self.active_channels = []
        # Check if instrumental is done playing
        if (
            self.instrumental_channel is not None
            and not self.instrumental_channel.get_busy()
        ):
            self.instrumental_channel = None
        # Process soundscapes list
        for soundscape in soundscapes:
            sound_id = str(soundscape["id"])
            track_gain = soundscape.get("gain", {"global": 1.0})
            track_path = manifest[sound_id]["path"]
            global_gain = track_gain.get("global", 1.0)
            sound = pygame.mixer.Sound(track_path)
            channel = pygame.mixer.find_channel()
            # Skip if this is the reserved instrumental channel
            if channel == self.instrumental_channel:
                channel = pygame.mixer.find_channel()
            if channel and channel != self.instrumental_channel:
                channel.set_volume(global_gain)
                channel.play(sound, loops=-1, fade_ms=6000)  # loops=-1 (infinite)
                self.active_channels.append(channel)
        # Process instrumental list only if no instrumental is currently playing
        if (
            self.instrumental_channel is None
            or not self.instrumental_channel.get_busy()
        ):
            self.instrumental_channel = None
            for inst in instrumental:
                sound_id = str(inst["id"])
                track_gain = inst.get("gain", {"global": 1.0})
                track_path = manifest[sound_id]["path"]
                global_gain = track_gain.get("global", 1.0)
                sound = pygame.mixer.Sound(track_path)
                channel = pygame.mixer.find_channel()
                if channel:
                    channel.set_volume(global_gain)
                    channel.play(sound, loops=0, fade_ms=6000)  # loops=0 (play once)
                    self.instrumental_channel = channel
