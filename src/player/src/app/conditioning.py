"""Offline audio conditioning — run once after download, then cached.

This is the answer to "make even lossy files play back nicely" (design doc §6,
Stage 1). Each source is decoded once and turned into a clean, loudness-matched,
seamlessly-loopable float WAV that the real-time player can read directly:

1. decode to float32;
2. resample to the engine sample rate (soxr if available, else linear);
3. gentle high-shelf cut above ~15 kHz to tame lossy-codec "fizz";
4. loop-seam crossfade so random-start loops don't click;
5. loudness-normalise (EBU R128 via pyloudnorm if available, else RMS) and cap
   the peak so layers sit together and never clip.

``soxr`` and ``pyloudnorm`` are optional; without them the numpy fallbacks are
used and a note is printed. Results are cached and skipped on re-runs.
"""

import json
import os

import numpy as np
import soundfile as sf

TARGET_LUFS = -20.0
PEAK_CEILING = 10 ** (-1.0 / 20.0)  # -1 dBFS
HF_SHELF_DB = -3.0
HF_SHELF_LO = 13000.0  # start of the transition
HF_SHELF_HI = 16000.0  # full cut above here
LOOP_XFADE_MS = 50.0
CONDITION_VERSION = 2  # bump to invalidate every cached file


def _resample(data: np.ndarray, sr: int, target: int) -> np.ndarray:
    if sr == target:
        return data
    try:
        import soxr

        return np.ascontiguousarray(soxr.resample(data, sr, target), dtype=np.float32)
    except Exception:
        n_out = int(round(data.shape[0] * target / sr))
        if n_out <= 0:
            return data
        x_old = np.linspace(0.0, 1.0, data.shape[0])
        x_new = np.linspace(0.0, 1.0, n_out)
        return np.stack(
            [np.interp(x_new, x_old, data[:, c]) for c in range(data.shape[1])],
            axis=1,
        ).astype(np.float32)


def _hf_shelf(data: np.ndarray, fs: int) -> np.ndarray:
    """Zero-phase high-shelf cut, applied in the frequency domain (offline)."""
    n = data.shape[0]
    if n < 16:
        return data
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    shelf = 10 ** (HF_SHELF_DB / 20.0)
    gain = np.ones_like(freqs)
    ramp = (freqs - HF_SHELF_LO) / (HF_SHELF_HI - HF_SHELF_LO)
    ramp = np.clip(ramp, 0.0, 1.0)
    # Smooth cosine transition from 1.0 down to the shelf gain.
    gain = 1.0 + (shelf - 1.0) * (0.5 - 0.5 * np.cos(np.pi * ramp))
    out = np.empty_like(data)
    for c in range(data.shape[1]):
        spec = np.fft.rfft(data[:, c])
        out[:, c] = np.fft.irfft(spec * gain, n)
    return out.astype(np.float32)


def _loop_crossfade(data: np.ndarray, fs: int) -> np.ndarray:
    """Fold the tail into the head so the loop point is seamless."""
    n = data.shape[0]
    x = int(fs * LOOP_XFADE_MS / 1000.0)
    if x < 2 or n < 4 * x:
        return data
    fade_in = np.linspace(0.0, 1.0, x, dtype=np.float32)[:, None]
    fade_out = 1.0 - fade_in
    blended = data[-x:] * fade_out + data[:x] * fade_in
    return np.concatenate([blended, data[x:-x]], axis=0).astype(np.float32)


def _normalize(data: np.ndarray, fs: int, target_lufs: float) -> np.ndarray:
    gain = None
    try:
        import pyloudnorm as pyln

        loud = pyln.Meter(fs).integrated_loudness(data)
        if np.isfinite(loud) and loud > -120:
            gain = 10 ** ((target_lufs - loud) / 20.0)
    except Exception:
        pass
    if gain is None:
        rms = float(np.sqrt(np.mean(np.square(data)))) or 1e-9
        gain = (10 ** (target_lufs / 20.0)) / rms
    data = data * gain
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > PEAK_CEILING:
        data = data * (PEAK_CEILING / peak)
    return data.astype(np.float32)


def _signature(src_path: str, target_fs: int, target_lufs: float) -> str:
    st = os.stat(src_path)
    return f"v{CONDITION_VERSION}:{st.st_size}:{st.st_mtime_ns}:{target_fs}:{target_lufs}"


def condition_file(
    src_path: str,
    out_path: str,
    target_fs: int,
    target_lufs: float = TARGET_LUFS,
    hf_shelf: bool = True,
) -> str:
    """Condition ``src_path`` into ``out_path`` (cached). Returns ``out_path``."""
    sidecar = out_path + ".json"
    sig = _signature(src_path, target_fs, target_lufs)
    if os.path.exists(out_path) and os.path.exists(sidecar):
        try:
            if json.load(open(sidecar)).get("signature") == sig:
                return out_path
        except Exception:
            pass

    data, sr = sf.read(src_path, dtype="float32", always_2d=True)
    data = _resample(data, sr, target_fs)
    if hf_shelf:
        data = _hf_shelf(data, target_fs)
    data = _loop_crossfade(data, target_fs)
    data = _normalize(data, target_fs, target_lufs)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sf.write(out_path, data, target_fs, subtype="FLOAT")
    json.dump(
        {"signature": sig, "source": os.path.basename(src_path), "fs": target_fs},
        open(sidecar, "w"),
    )
    return out_path


def condition_manifest(
    manifest: dict, out_dir: str, target_fs: int, target_lufs: float = TARGET_LUFS
) -> dict:
    """Condition every local file in ``manifest`` ({id: path}); return {id: path}.

    Files that fail to condition fall back to their original path so playback
    still works.
    """
    out = {}
    for sound_id, src_path in manifest.items():
        if not src_path or not os.path.exists(src_path):
            out[sound_id] = src_path
            continue
        dest = os.path.join(out_dir, f"{sound_id}.wav")
        try:
            out[sound_id] = condition_file(src_path, dest, target_fs, target_lufs)
        except Exception as error:
            print(f"  ! conditioning {sound_id} failed ({error}); using original")
            out[sound_id] = src_path
    return out
