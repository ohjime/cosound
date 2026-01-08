import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env" / ".env")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import json
import pygame

MANIFEST_PATH = Path(__file__).parent.parent.parent / "manifest.json"

pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=4096)
pygame.mixer.set_num_channels(16)


class LayerManager:

    def __init__(self):
        self.active_channels = []

    def transition(self, cosound):
        with open(MANIFEST_PATH, "r") as f:
            manifest = json.load(f)
        for ch in self.active_channels:
            ch.fadeout(6000)
        self.active_channels = []
        for sound_id, track_gain in cosound.items():
            track_path = manifest[sound_id]["path"]
            global_gain = track_gain["global"]
            sound = pygame.mixer.Sound(track_path)
            channel = pygame.mixer.find_channel()
            if channel:
                channel.set_volume(global_gain)
                channel.play(sound, loops=-1, fade_ms=6000)  # loops=-1 (infinite)
                self.active_channels.append(channel)
