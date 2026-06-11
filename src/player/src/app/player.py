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
    @staticmethod
    def available_output_devices():
        return [
            (index, device)
            for index, device in enumerate(sd.query_devices())
            if int(device.get("max_output_channels", 0)) > 0
        ]

    def __init__(
        self,
        channels=0,
        fs=44100,
        fade_time_ms=8000,
        blocksize=1024,
        master_gain=0.7,
        device=None,
    ):
        self.fs = fs
        self.master_gain = float(master_gain)
        self.device, self.device_info = self._resolve_output_device(device)
        self.channels = self._resolve_output_channels(channels, self.device_info)
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

        # Keep optional attenuation for some channels in wider layouts.
        self.channel_gains = self._default_channel_gains(self.channels)

        # Initialize Stream
        self.stream = sd.OutputStream(
            samplerate=self.fs,
            channels=self.channels,
            device=self.device,
            callback=self._audio_callback,
            blocksize=blocksize,
            dtype="float32",
        )
        self.stream.start()

    def set_master_gain(self, gain):
        with self.lock:
            self.master_gain = max(0.0, min(1.0, float(gain)))

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
            data, _ = sf.read(path, dtype="float32", always_2d=True)
            data = self._adapt_channels_for_output(data)

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
                chunk = data[indices, :]

                target = track["target_gain"]
                current = track["curr_gain"]
                if current != target:
                    if self.fade_samples <= 1:
                        ramp = np.full(frames, target, dtype=np.float32)
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
                    ramp = np.full(frames, current, dtype=np.float32)

                outdata += chunk * ramp[:, np.newaxis]

                track["ptr"] = (track["ptr"] + frames) % len(data)

                if track["curr_gain"] <= 0 and track["target_gain"] == 0:
                    del self.active_tracks[path]

        np.multiply(outdata, self.channel_gains, out=outdata)
        np.multiply(outdata, self.master_gain, out=outdata)
        np.clip(outdata, -1.0, 1.0, out=outdata)

    def _default_channel_gains(self, channels):
        gains = np.ones(channels, dtype=np.float32)
        if channels >= 8:
            gains[6:8] = 0.5
        return gains

    def _resolve_output_channels(self, requested_channels, output_info):
        requested = int(requested_channels) if requested_channels else 0
        max_channels = int((output_info or {}).get("max_output_channels", 0))

        if max_channels <= 0:
            return requested if requested > 0 else 1

        if requested <= 0:
            return max_channels

        if requested > max_channels:
            print(
                "Requested %s output channels, but device supports %s. Using %s."
                % (requested, max_channels, max_channels)
            )
            return max_channels

        return requested

    def _resolve_output_device(self, device):
        if device is None:
            info = self._query_output_device_info(None)
            print("Using default output device")
            pprint(info)
            return None, info

        normalized = int(device) if str(device).isdigit() else device
        info = self._query_output_device_info(normalized)
        if info:
            print(f"Using output device: {normalized}")
            pprint(info)
            return normalized, info

        name = str(device).lower()
        matches = []
        for index, candidate in enumerate(sd.query_devices()):
            if int(candidate.get("max_output_channels", 0)) <= 0:
                continue
            if name in str(candidate.get("name", "")).lower():
                matches.append((index, candidate))

        if not matches:
            raise ValueError(f"No output device matched '{device}'.")

        selected_index, selected_info = matches[0]
        print(f"Using output device by name match: {selected_index}")
        pprint(selected_info)
        return selected_index, selected_info

    def _query_output_device_info(self, device):
        try:
            kwargs = {"kind": "output"}
            if device is not None:
                kwargs["device"] = device
            return sd.query_devices(**kwargs)
        except Exception:
            return None

    def _adapt_channels_for_output(self, data):
        samples, in_channels = data.shape
        out_channels = self.channels

        if out_channels == in_channels:
            return data

        if in_channels == 1:
            return np.repeat(data, out_channels, axis=1)

        if in_channels == 2:
            if out_channels == 1:
                return data.mean(axis=1, keepdims=True)

            out = np.zeros((samples, out_channels), dtype=np.float32)
            left_targets = list(range(0, out_channels, 2))
            right_targets = list(range(1, out_channels, 2))

            if not left_targets:
                left_targets = [0]
            if not right_targets:
                right_targets = left_targets

            left_weight = 1.0 / np.sqrt(len(left_targets))
            right_weight = 1.0 / np.sqrt(len(right_targets))

            out[:, left_targets] = data[:, [0]] * left_weight
            out[:, right_targets] = data[:, [1]] * right_weight
            return out

        out = np.zeros((samples, out_channels), dtype=np.float32)
        for out_ch in range(out_channels):
            out[:, out_ch] = data[:, out_ch % in_channels]
        return out
