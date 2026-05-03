from abc import ABC, abstractmethod
import threading
import numpy as np
import sounddevice as sd
import soundfile as sf
from pprint import pprint


class CommunalPlayer(ABC):
    @abstractmethod
    def queue_sound(self, sound_path, gain):
        raise NotImplementedError

    @abstractmethod
    def dequeue_cosound(self):
        raise NotImplementedError


class SoundDevicePlayer(CommunalPlayer):
    def __init__(self, channels=8, fs=44100, fade_time_ms=8000, blocksize=1024):
        self.fs = fs
        requested_channels = int(channels) if channels else 0
        if requested_channels <= 0:
            requested_channels = 1
        self.channels = self._resolve_output_channels(requested_channels)
        fade_time_sec = fade_time_ms / 1000.0
        if fade_time_sec <= 0:
            self.fade_samples = 1
        else:
            self.fade_samples = int(self.fs * fade_time_sec)
            if self.fade_samples < 1:
                self.fade_samples = 1

        # State Management
        self.active_tracks = {}
        self.pending_queue = {}
        self.lock = threading.Lock()

        # Speaker Group Mapping (Example: 8-channel setup)
        self.speaker_groups = self._default_speaker_groups(self.channels)
        self._validate_speaker_groups()

        # Multipliers for specific groups (e.g., lower the ceiling)
        self.group_gains = {group: 1.0 for group in self.speaker_groups}
        if "ceiling" in self.group_gains:
            self.group_gains["ceiling"] = 0.5

        # Initialize Stream
        self.stream = sd.OutputStream(
            samplerate=self.fs,
            channels=self.channels,
            callback=self._audio_callback,
            blocksize=blocksize,
            dtype="float32",
        )
        self.stream.start()

    def queue_sound(self, sound_path, gain):
        """Prepares a sound to be transitioned into the mix."""
        with self.lock:
            self.pending_queue[str(sound_path)] = float(gain)

    def dequeue_cosound(self):
        """Triggers the transition: fades out old tracks and fades in new ones."""
        with self.lock:
            pending = dict(self.pending_queue)
            self.pending_queue = {}

            # Any track currently playing that ISN'T in the new queue should fade to 0
            for path in list(self.active_tracks.keys()):
                if path not in pending:
                    self.active_tracks[path]["target_gain"] = 0.0

        if not pending:
            return

        # Load audio outside the lock to avoid blocking the real-time callback.
        new_tracks = {}
        for path, target_gain in pending.items():
            data, _ = sf.read(path, dtype="float32")
            if data.ndim > 1:
                data = data.mean(axis=1)

            if data.size == 0:
                continue

            new_tracks[path] = {
                "data": data,
                "ptr": 0,
                "curr_gain": 0.0,
                "target_gain": float(target_gain),
            }

        with self.lock:
            # Add new tracks or update target gains for existing ones
            for path, target_gain in pending.items():
                track = self.active_tracks.get(path)
                if track:
                    track["target_gain"] = float(target_gain)
                    continue

                new_track = new_tracks.get(path)
                if new_track:
                    self.active_tracks[path] = new_track

    def _audio_callback(self, outdata, frames, time, status):
        """The real-time audio thread."""
        if status:
            print(status)

        outdata.fill(0)

        with self.lock:
            for path in list(self.active_tracks.keys()):
                track = self.active_tracks[path]
                data = track["data"]
                if data.size == 0:
                    del self.active_tracks[path]
                    continue

                indices = (np.arange(track["ptr"], track["ptr"] + frames)) % len(data)
                chunk = data[indices]

                target = track["target_gain"]
                current = track["curr_gain"]
                if current != target:
                    if self.fade_samples <= 1:
                        ramp = target
                        track["curr_gain"] = float(target)
                    else:
                        step = (target - current) / self.fade_samples
                        ramp_end = current + (step * frames)
                        ramp = np.linspace(current, ramp_end, frames)
                        if target > current:
                            ramp = np.minimum(ramp, target)
                        else:
                            ramp = np.maximum(ramp, target)
                        track["curr_gain"] = float(ramp[-1]) if frames > 0 else current
                else:
                    ramp = current

                for group, channel_indices in self.speaker_groups.items():
                    group_mult = self.group_gains.get(group, 1.0)
                    outdata[:, channel_indices] += (chunk * ramp * group_mult)[
                        :, np.newaxis
                    ]

                track["ptr"] = (track["ptr"] + frames) % len(data)

                if track["curr_gain"] <= 0 and track["target_gain"] == 0:
                    del self.active_tracks[path]

    def _default_speaker_groups(self, channels):
        if channels >= 8:
            return {
                "mains": [0, 1, 2, 3],
                "subs": [4, 5],
                "ceiling": [6, 7],
            }

        return {"mains": list(range(channels))}

    def _resolve_output_channels(self, requested_channels):
        output_info = self._get_default_output_info()
        pprint(output_info)
        if not output_info:
            return requested_channels

        max_channels = int(output_info.get("max_output_channels", 0))
        if max_channels <= 0:
            return requested_channels

        if requested_channels > max_channels:
            print(
                "Requested %s output channels, but device supports %s. Using %s."
                % (requested_channels, max_channels, max_channels)
            )
            return max_channels

        return requested_channels

    def _get_default_output_info(self):
        try:
            return sd.query_devices(kind="output")
        except Exception:
            return None

    def _validate_speaker_groups(self):
        for group, channel_indices in self.speaker_groups.items():
            for channel in channel_indices:
                if channel < 0 or channel >= self.channels:
                    raise ValueError(
                        f"Speaker group '{group}' has invalid channel index {channel}."
                    )
