"""
Audio player module for handling playback and transitions.
Simplified: single OutputStream mixes up to two tracks to do a real 30s crossfade.
"""
import threading
import numpy as np
import librosa
import sounddevice as sd
from pathlib import Path
from typing import Optional, List, Dict
import logging

from .config import BUFFER_SIZE, DEFAULT_FADE_DURATION

logger = logging.getLogger(__name__)


class Player:
    """
    Minimal player that keeps a single OutputStream and mixes up to two tracks:
    - track A: current playing (can fade out)
    - track B: next track (fades in)
    """

    def __init__(self, sr: int = 44100):
        self.sr = sr
        self.stream: Optional[sd.OutputStream] = None
        # Each track: {buffer, pos, fade_total, fade_prog, direction, name}
        self._tracks: List[Dict] = []
        self._lock = threading.RLock()
        self._playing: Optional[str] = None

    def _ensure_stream(self):
        if self.stream is None:
            self.stream = sd.OutputStream(
                samplerate=self.sr,
                channels=1,
                callback=self._callback,
                blocksize=BUFFER_SIZE,
            )
            self.stream.start()
            logger.info("Audio stream started")

    def _callback(self, outdata, frames, time, status):
        with self._lock:
            if not self._tracks:
                outdata.fill(0)
                return

            mix = np.zeros(frames, dtype=np.float32)

            finished_idx = []
            for i, tr in enumerate(self._tracks):
                buf = tr["buffer"]
                pos = tr["pos"]
                if pos >= len(buf):
                    finished_idx.append(i)
                    continue

                n = min(frames, len(buf) - pos)
                seg = buf[pos:pos + n].astype(np.float32)

                # Envelope
                if tr["direction"] == "in" and tr["fade_total"] > 0:
                    start_g = min(1.0, tr["fade_prog"] / tr["fade_total"])
                    end_g = min(1.0, (tr["fade_prog"] + n) / tr["fade_total"])
                    env = np.linspace(start_g, end_g, n, endpoint=False, dtype=np.float32)
                elif tr["direction"] == "out" and tr["fade_total"] > 0:
                    start_g = max(0.0, 1.0 - tr["fade_prog"] / tr["fade_total"])
                    end_g = max(0.0, 1.0 - (tr["fade_prog"] + n) / tr["fade_total"])
                    env = np.linspace(start_g, end_g, n, endpoint=False, dtype=np.float32)
                else:
                    env = np.ones(n, dtype=np.float32)

                mix[:n] += seg * env

                tr["pos"] = pos + n
                tr["fade_prog"] += n

                # Transition completion checks
                if tr["direction"] == "in" and tr["fade_prog"] >= tr["fade_total"]:
                    tr["direction"] = "none"
                if tr["direction"] == "out" and tr["fade_prog"] >= tr["fade_total"]:
                    finished_idx.append(i)

            # Remove finished tracks (from end to start)
            for idx in reversed(finished_idx):
                # If we remove the first (old) and second remains, mark as playing
                removed = self._tracks.pop(idx)
                if removed.get("name") == self._playing and self._tracks:
                    # Make sure playing reflects the newest track if any
                    self._playing = self._tracks[-1].get("name")

            # Output mono audio
            outdata[:, 0] = 0.0
            outdata[:len(mix), 0] = mix

    def _load_audio(self, sound: str) -> np.ndarray:
        audio_path = Path(__file__).parent.parent / ".audio" / sound
        if not audio_path.exists():
            raise FileNotFoundError(f"Sound file not found: {audio_path}")
        # Always load/resample to player SR to avoid stream restarts
        y, sr = librosa.load(str(audio_path), sr=self.sr, mono=True)
        return y.astype(np.float32)

    def play(self, sound: Optional[str] = None) -> None:
        # Choose random file if not provided
        if sound is None:
            import random
            sounds_dir = Path(__file__).parent.parent / ".audio"
            if not sounds_dir.exists():
                logger.error(f".audio/ directory not found at {sounds_dir}")
                return
            files = sum([
                list(sounds_dir.glob("*.wav")),
                list(sounds_dir.glob("*.mp3")),
                list(sounds_dir.glob("*.ogg")),
            ], [])
            if not files:
                logger.error("No sound files found in .audio/ directory")
                return
            sound = random.choice(files).name

        try:
            y = self._load_audio(sound)
            with self._lock:
                # Replace any existing tracks with the new one immediately
                self._tracks = [{
                    "buffer": y,
                    "pos": 0,
                    "fade_total": 0,
                    "fade_prog": 0,
                    "direction": "none",
                    "name": sound,
                }]
                self._playing = sound
                logger.info(f"Now playing: {sound} ({len(y)/self.sr:.2f}s)")
            self._ensure_stream()
        except Exception as e:
            logger.error(f"Error loading sound {sound}: {e}")

    def transition(self, sound: str, duration: float = 30.0) -> None:
        """Crossfade to a new sound over `duration` seconds without stopping the stream."""
        try:
            y_new = self._load_audio(sound)
            fade_samples = int(max(0.0, duration) * self.sr)
            with self._lock:
                # Mark existing first track (if any) to fade out
                if self._tracks:
                    # Only the oldest (index 0) needs to fade out; allow newest to remain
                    # Keep at most 1 old + 1 new
                    old = self._tracks[-1]
                    old["direction"] = "out"
                    old["fade_total"] = fade_samples
                    old["fade_prog"] = 0

                # Add new track fading in
                self._tracks.append({
                    "buffer": y_new,
                    "pos": 0,
                    "fade_total": fade_samples,
                    "fade_prog": 0,
                    "direction": "in",
                    "name": sound,
                })

                # Only keep last two tracks to keep mixer simple
                if len(self._tracks) > 2:
                    self._tracks = self._tracks[-2:]

                # Set the new one as "playing" title
                self._playing = sound

            self._ensure_stream()
            logger.info(f"Crossfading to: {sound} over {duration:.1f}s")
        except Exception as e:
            logger.error(f"Error during transition to {sound}: {e}")

    def get_playing(self) -> Optional[str]:
        with self._lock:
            return self._playing

    def stop(self) -> None:
        with self._lock:
            self._tracks.clear()
            self._playing = None
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None
        logger.info("Audio stream stopped")


# Singleton instance and module-level API for backward compatibility
_PLAYER = Player()


def play(sound: Optional[str] = None) -> None:
    _PLAYER.play(sound)


def transition(sound: str) -> None:
    # Force 30s as requested
    _PLAYER.transition(sound, duration=30.0)


def get_playing() -> Optional[str]:
    return _PLAYER.get_playing()


def stop() -> None:
    _PLAYER.stop()