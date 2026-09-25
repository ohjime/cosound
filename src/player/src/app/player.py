from abc import ABC, abstractmethod
import random
import threading
from time import monotonic
import numpy as np
import sounddevice as sd
import soundfile as sf

from app.devices import detect_output, list_output_devices
from app.layout import infer_layout, default_source_azimuths
from app.spatial import make_renderer
from app.reverb import FDNReverb
from app.conditioning import _resample as resample_audio
from app.sync import ServerClock
from app.playback import PlaybackPlan, loop_chunk
from app.chime import (
    VOTE_CHIME_DEFAULT_VOLUME,
    VOTE_CHIME_DOWNVOTE_DEGREES,
    VOTE_CHIME_MAX_RATIO,
    VOTE_CHIME_OUTPUT_CEILING,
    VOTE_CHIME_RMS_FLOOR,
    VOTE_CHIME_RMS_SECONDS,
    VOTE_CHIME_UPVOTE_DEGREES,
    chime_loudness,
    vote_chime_scale,
)


def _levels_of(buffers, sample_rate):
    """Measure a prepared scale: (peak sample, loudest short-window RMS).

    Both come from the loudest degree rather than from each degree separately,
    so re-levelling moves the whole scale together and leaves the balance
    between its degrees as the chime was designed.
    """
    sounding = [buffer for buffer in buffers if len(buffer)]
    if not sounding:
        return 0.0, 0.0
    peak = max(float(np.max(np.abs(buffer))) for buffer in sounding)
    loudness = max(chime_loudness(buffer, sample_rate) for buffer in sounding)
    return peak, loudness


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
        return list_output_devices()

    def __init__(
        self,
        channels=0,
        fs=None,
        fade_time_ms=8000,
        blocksize=1024,
        master_gain=0.7,
        device=None,
        layout_override=None,
        reverb_room=0.5,
        reverb_amount=0.35,
        rotation_deg_per_s=0.0,
    ):
        # --- Resolve and probe the output device (auto-detect, see devices.py) ---
        self.device_obj = detect_output(device)
        if channels and int(channels) > 0:
            requested = int(channels)
            # An assumed count is a guess, not a ceiling — a plugin device will
            # accept whatever we ask for, so an explicit request wins outright.
            self.device_obj.channels = (
                requested
                if self.device_obj.channels_assumed
                else min(requested, self.device_obj.channels)
            )
            self.device_obj.channels_assumed = False
        self.device = self.device_obj.index
        self.device_info = self.device_obj.raw or {"name": self.device_obj.name}
        self.channels = self.device_obj.channels
        # Default to the device's own sample rate unless overridden.
        self.fs = int(fs) if fs else int(self.device_obj.samplerate)
        self.master_gain = float(master_gain)

        # --- Infer speaker layout and build the spatial renderer + reverb ---
        self.layout = infer_layout(self.device_obj, layout_override)
        self.renderer = make_renderer(
            self.layout, self.fs, rotation_deg_per_s=rotation_deg_per_s
        )
        self.reverb = FDNReverb(
            self.channels, self.fs, room=reverb_room, amount=reverb_amount
        )

        fade_time_sec = fade_time_ms / 1000.0
        if fade_time_sec <= 0:
            self.fade_samples = 1
        else:
            self.fade_samples = max(1, int(self.fs * fade_time_sec))

        # State Management
        self.active_tracks = {}
        self.pending_queue = {}
        self.lock = threading.Lock()
        self.muted = False
        self.levels = {}
        self.last_status = None
        self.clock = ServerClock()
        self._sync_plans = []
        self._scheduled_chimes = []
        self._dac_timing_available = False
        self._audio_clock_anchor = None
        # One finished buffer per degree of the scale in app.chime, plus a
        # cursor into whichever degree each in-flight acknowledgement is using.
        self._default_vote_chime = vote_chime_scale(self.fs)
        self._vote_chime = self._default_vote_chime
        self._vote_chime_positions = []
        self._vote_chime_degree = -1
        # A one-shot is levelled against the soundscape it interrupts rather
        # than against full scale, so an acknowledgement keeps the same
        # prominence in a sparse mix and a dense one.  That needs how loud the
        # prepared buffers actually are, measured once here, and a slow average
        # of the mix, maintained by the callback.
        self._vote_chime_peak, self._vote_chime_loudness = _levels_of(
            self._default_vote_chime, self.fs
        )
        self._vote_chime_volume = VOTE_CHIME_DEFAULT_VOLUME
        self._mix_rms = 0.0

        # Source positions for layered tracks (AAS used an even 45° spread).
        self._positions = default_source_azimuths(8)
        self._pos_idx = 0

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
        self._capture_audio_clock()

    # --- Controls -----------------------------------------------------------

    def set_master_gain(self, gain):
        with self.lock:
            self.master_gain = max(0.0, min(1.0, float(gain)))

    def play_vote_chime(self, pleasant=None, *, play_at=None, vote_id=None):
        """Start a one-shot on the existing output, independently of mix changes."""
        with self.lock:
            if pleasant == 0 and type(pleasant) is int:
                degrees = VOTE_CHIME_DOWNVOTE_DEGREES
            elif pleasant == 1 and type(pleasant) is int:
                degrees = VOTE_CHIME_UPVOTE_DEGREES
            else:
                degrees = range(len(self._vote_chime))
            if play_at is not None and type(vote_id) is int:
                # Every replica chooses the same voice, regardless of missed
                # votes or when this process was started.
                degree = degrees[vote_id % len(degrees)]
                self._scheduled_chimes = self._scheduled_chimes[-7:] + [(degree, play_at)]
                return
            # Pick freely within the consonant set, avoiding an immediate repeat.
            choices = [degree for degree in degrees if degree != self._vote_chime_degree]
            self._vote_chime_degree = random.choice(choices)
            # Bound burst cost while allowing new taps to sound immediately.
            self._vote_chime_positions = self._vote_chime_positions[-7:] + [
                (self._vote_chime_degree, 0)
            ]

    def set_vote_chime(self, samples=None):
        """Atomically install a prepared one-shot, or reset to the built-in tone."""
        if samples is None:
            prepared = self._default_vote_chime
        else:
            base = np.asarray(samples)
            if base.ndim != 1 or base.size == 0:
                raise ValueError("Vote chime must be a non-empty mono buffer")
            if not np.isfinite(base).all():
                raise ValueError("Vote chime contains non-finite samples")
            # Repitch the whole scale here, off the audio thread.  This also
            # copies, so a caller cannot mutate data the callback is reading.
            prepared = vote_chime_scale(self.fs, base)
        peak, loudness = _levels_of(prepared, self.fs)
        with self.lock:
            self._vote_chime = prepared
            self._vote_chime_peak = peak
            self._vote_chime_loudness = loudness
            # A playback cursor into the old buffers may be beyond the end of a
            # shorter replacement.  Dropping an in-flight acknowledgement makes
            # the swap safe; the next vote starts the new sound immediately.
            self._vote_chime_positions = []
            self._scheduled_chimes = []

    def set_vote_chime_volume(self, volume):
        """Set how loud an acknowledgement is against the mix, from 0 to 1."""
        volume = float(volume)
        if not np.isfinite(volume):
            raise ValueError("Vote chime volume must be a finite number")
        with self.lock:
            self._vote_chime_volume = max(0.0, min(1.0, volume))

    def set_muted(self, muted):
        with self.lock:
            self.muted = bool(muted)

    def toggle_mute(self):
        with self.lock:
            self.muted = not self.muted
            return self.muted

    def set_reverb(self, room=None, amount=None):
        if room is not None:
            self.reverb.set_room(room)
        if amount is not None:
            self.reverb.set_amount(amount)

    def get_levels(self):
        """Latest per-track output peaks as {sound_path: peak in [0, 1]}."""
        with self.lock:
            return dict(self.levels)

    # --- Queueing -----------------------------------------------------------

    def queue_sound(self, sound_path, gain):
        """Prepares a sound to be transitioned into the mix."""
        with self.lock:
            self.pending_queue[str(sound_path)] = float(gain)

    def _assign_azimuth(self):
        if not self._positions:
            return 0.0
        az = self._positions[self._pos_idx % len(self._positions)]
        self._pos_idx += 1
        return az

    def dequeue_cosound(self):
        """Triggers the transition: fades out old tracks and fades in new ones."""
        with self.lock:
            # A rolling server downgrade can remove the optional timeline.
            # Convert existing tracks before returning to the legacy mixer.
            plans = getattr(self, "_sync_plans", [])
            if plans:
                now = self.clock.server_time()
                for track in self.active_tracks.values():
                    gain = 0.0
                    if now is not None:
                        for plan in plans:
                            if now >= plan.effective_at:
                                gain = float(plan.gains(track.get("sound_id"), np.array([now]))[0])
                    track.update(ptr=int(track.get("sync_ptr", 0)),
                                 curr_gain=gain, target_gain=gain)
                self._sync_plans = []
            pending = dict(self.pending_queue)
            self.pending_queue = {}

            # Any track currently playing that ISN'T in the new queue fades to 0.
            for path in list(self.active_tracks.keys()):
                if path not in pending:
                    self.active_tracks[path]["target_gain"] = 0.0

        if not pending:
            return

        # Load audio outside the lock to avoid blocking the real-time callback.
        new_tracks = {}
        for path, target_gain in pending.items():
            data, sr = sf.read(path, dtype="float32", always_2d=True)
            if sr != self.fs:
                data = resample_audio(data, sr, self.fs)
            if data.size == 0:
                continue
            new_tracks[path] = {
                "data": data,
                "ptr": 0,
                "curr_gain": 0.0,
                "target_gain": float(target_gain),
            }

        with self.lock:
            for path, target_gain in pending.items():
                track = self.active_tracks.get(path)
                if track:
                    track["target_gain"] = float(target_gain)
                    continue
                new_track = new_tracks.get(path)
                if new_track:
                    new_track["azimuth"] = self._assign_azimuth()
                    self.active_tracks[path] = new_track

    def schedule_cosound(self, manifest, layers, descriptor):
        """Prepare a server timeline off the audio thread, then install atomically."""
        plan = PlaybackPlan.parse(descriptor, layers)
        with self.lock:
            if self._sync_plans and (
                plan.revision == self._sync_plans[-1].revision
                or plan.effective_at < self._sync_plans[-1].effective_at
            ):
                return
            existing = dict(self.active_tracks)
        prepared = {}
        for sound_id in plan.previous.keys() | plan.target.keys():
            if not (plan.previous.get(sound_id) or plan.target.get(sound_id)):
                continue
            path = manifest.get(sound_id)
            if not path:
                if not plan.target.get(sound_id):
                    continue
                raise ValueError(f"Missing synchronized sound {sound_id}")
            path = str(path)
            if path in existing and existing[path].get("sound_id") == sound_id:
                prepared[path] = existing[path]
                continue
            try:
                data, sr = sf.read(path, dtype="float32", always_2d=True)
                if not len(data) or not np.isfinite(data).all():
                    raise ValueError(f"Invalid synchronized sound {sound_id}")
            except Exception:
                if not plan.target.get(sound_id):
                    continue
                raise
            duration = len(data) / sr
            if sr != self.fs:
                data = resample_audio(data, sr, self.fs)
            prepared[path] = {
                "data": data, "duration": duration, "sound_id": sound_id,
                "azimuth": self._positions[int(sound_id) % len(self._positions)],
            }
        with self.lock:
            if not self.clock.ready or not self._dac_timing_available:
                # Nothing synchronized is audible yet. An unavailable clock
                # or driver must not accumulate every revision and audio file.
                self.active_tracks = prepared
                self._sync_plans = [plan]
            else:
                self.active_tracks.update(prepared)
                # Keep earlier queued deadlines until the callback passes them.
                self._sync_plans.append(plan)

    def get_sync_status(self):
        """Diagnostics describe the estimate, not measured acoustic accuracy."""
        self._capture_audio_clock()
        with self.lock:
            return {
                "clock_ready": self.clock.ready,
                "timeline_active": bool(self._sync_plans),
                "dac_timing_available": self._dac_timing_available,
                "phase_error_ms": max((abs(t.get("sync_error_ms", 0))
                                       for t in self.active_tracks.values()), default=0),
            }

    def _capture_audio_clock(self):
        """Bridge the device clock off the callback, where PortAudio allows it.

        Called by the existing UI meter timer. Bracketing bounds scheduling
        jitter; skip delayed readings instead of moving all audible samples.
        """
        before = monotonic()
        try:
            stream_time = self.stream.time
        except sd.PortAudioError:
            self._audio_clock_anchor = None
            return
        after = monotonic()
        if np.isfinite(stream_time) and after - before <= 0.001:
            self._audio_clock_anchor = (stream_time, (before + after) / 2)

    def _server_output_time(self, timing):
        clock = getattr(self, "clock", None)
        if clock is None or timing is None:
            return None
        current = float(timing.currentTime)
        dac = float(timing.outputBufferDacTime)
        anchor = getattr(self, "_audio_clock_anchor", None)
        valid = (anchor is not None and np.isfinite(current) and np.isfinite(dac)
                 and dac > 0 and dac >= current)
        self._dac_timing_available = bool(valid)
        if not valid:
            return None
        # Python/GIL delays after PortAudio invoked us do not change this
        # deadline. No PortAudio API is called on the real-time audio thread.
        return clock.server_time(anchor[1] + dac - anchor[0])

    def _synchronized_sources(self, frames, server_time):
        if server_time is None:
            return [], {}
        times = server_time + np.arange(frames) / self.fs
        plans = self._sync_plans
        sources, levels = [], {}
        for path, track in list(self.active_tracks.items()):
            sound_id = track.get("sound_id")
            if sound_id is None:
                del self.active_tracks[path]
                continue
            gain = np.zeros(frames)
            for plan in plans:
                mask = times >= plan.effective_at
                gain[mask] = plan.gains(sound_id, times[mask])
            # Loop origins stay fixed across gain changes, removals and rejoins.
            chunk = loop_chunk(track, frames, server_time, plans[-1].epoch, self.fs)
            signal = (chunk * gain[:, None]).astype(np.float32)
            sources.append({"signal": signal, "azimuth": track["azimuth"]})
            levels[path] = float(np.max(np.abs(signal))) if frames else 0.0

        # Retain the active envelope and future deadlines, not the entire run.
        while len(plans) > 1 and plans[1].effective_at <= server_time:
            plans.pop(0)
        needed = set()
        for plan in plans:
            needed.update(key for key, gain in plan.target.items() if gain)
            if server_time < plan.effective_at + plan.fade_seconds:
                needed.update(key for key, gain in plan.previous.items() if gain)
        for path, track in list(self.active_tracks.items()):
            if track.get("sound_id") not in needed:
                del self.active_tracks[path]
        return sources, levels

    # --- Real-time audio ----------------------------------------------------

    def _audio_callback(self, outdata, frames, time, status):
        """The real-time audio thread: gain-ramp tracks, then spatialise+reverb."""
        if status:
            self.last_status = status

        server_time = self._server_output_time(time)

        sources = []
        levels = {}

        with self.lock:
            chime = np.zeros(frames, dtype=np.float32)
            remaining = []
            for degree, position in self._vote_chime_positions:
                voice = self._vote_chime[degree]
                count = min(frames, len(voice) - position)
                chime[:count] += voice[position:position + count]
                if position + count < len(voice):
                    remaining.append((degree, position + count))
            self._vote_chime_positions = remaining
            if server_time is not None:
                scheduled = []
                for degree, play_at in getattr(self, "_scheduled_chimes", []):
                    voice = self._vote_chime[degree]
                    position = round((server_time - play_at) * self.fs)
                    start = max(0, -position)
                    end = min(frames, len(voice) - position)
                    if end > start:
                        chime[start:end] += voice[position + start:position + end]
                    if position + frames < len(voice):
                        scheduled.append((degree, play_at))
                self._scheduled_chimes = scheduled
            chime_volume = self._vote_chime_volume
            chime_peak = self._vote_chime_peak
            chime_loudness_level = self._vote_chime_loudness
            synchronized = bool(getattr(self, "_sync_plans", []))
            if synchronized:
                sources, levels = self._synchronized_sources(frames, server_time)
            for path in ([] if synchronized else list(self.active_tracks.keys())):
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

                gained = (chunk * ramp[:, np.newaxis]).astype(np.float32)
                sources.append({"signal": gained, "azimuth": track.get("azimuth")})
                if gained.size:
                    levels[path] = float(np.max(np.abs(gained)))

                track["ptr"] = (track["ptr"] + frames) % len(data)

                if track["curr_gain"] <= 0 and track["target_gain"] == 0:
                    del self.active_tracks[path]

            output_gain = 0.0 if self.muted else self.master_gain
            self.levels = {
                path: min(1.0, peak * output_gain) for path, peak in levels.items()
            }

        # Spatialise (positioned/decorrelated) + add the reverb return. These
        # objects are only ever touched here on the audio thread.
        if synchronized and server_time is not None and getattr(self.renderer, "rotation_deg_per_s", 0):
            self.renderer._angle = (
                (server_time - self._sync_plans[-1].epoch) * self.renderer.rotation_deg_per_s
            ) % 360.0
        dry, send = self.renderer.render(sources, frames)
        wet = self.reverb.process(send)
        mix = dry + wet

        # Average the mix's own level before the chime joins it, so the
        # measurement never chases the acknowledgement it is levelling.  A
        # one-pole over block RMS follows the soundscape rather than its
        # transients, and it is the raw level: master gain scales the chime and
        # the mix together further down, so turning the room down keeps the
        # balance between them.
        if frames:
            block_rms = float(np.sqrt(np.mean(np.square(mix), dtype=np.float64)))
            coefficient = 1.0 - np.exp(-frames / (self.fs * VOTE_CHIME_RMS_SECONDS))
            self._mix_rms += coefficient * (block_rms - self._mix_rms)
        # The floor keeps a vote audible in a silent or sleeping room, where
        # scaling by the mix alone would acknowledge nothing at all.
        reference = max(self._mix_rms, VOTE_CHIME_RMS_FLOOR)
        if chime_loudness_level > 0.0 and chime_peak > 0.0:
            # Match loudness to loudness: the one-shot's per-channel short-term
            # RMS lands on `volume` of the way up to VOTE_CHIME_MAX_RATIO times
            # the mix's own level, so volume 0.25 sits level with the soundscape
            # and 1.0 is unmistakable over it.
            spread = np.sqrt(self.channels)
            target = chime_volume * VOTE_CHIME_MAX_RATIO * reference
            chime_gain = min(
                target * spread / chime_loudness_level,
                # One acknowledgement must not reach the clipper on its own,
                # however loud the mix it is being levelled against.
                VOTE_CHIME_OUTPUT_CEILING * spread / chime_peak,
            )
            mix += chime[:, np.newaxis] * (chime_gain / spread)
        mix *= output_gain
        np.clip(mix, -1.0, 1.0, out=mix)
        outdata[:] = mix
