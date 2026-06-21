# Player Audio Fidelity & Spatialization — Analysis and Plan

**Status:** Implemented (Phase 1–2) · **Date:** 2026-06-16 · **Scope:** `src/player/`

**Implementation note (2026-06-16):** Phases 1 and 2 are built and offline-validated. New modules in `src/player/src/app/`: `devices.py` (auto-detect), `layout.py` (inference + mode select), `reverb.py` (FDN), `spatial.py` (VBAP + decorrelated upmix), `conditioning.py` (offline Stage 1). `player.py` now spatialises + reverberates in the callback and auto-detects the device sample rate; `main.py` conditions downloads to `src/player/conditioned/` before playback. Deps added: `soxr`, `pyloudnorm` (the latter pulls `scipy`); all guarded so the player still runs without them. Validated with `/tmp/validate_player.py` (layout inference, reverb decay/decorrelation, VBAP localisation + sub routing, upmix decorrelation, MP3/WAV conditioning, end-to-end callback). **Fix (post-review):** 2-channel/headphone outputs (e.g. AirPods) now use decorrelated stereo instead of a ±30° VBAP pair — the pair snapped off-arc sources to the nearest side and made layered scenes lean ~7× right; and source positions are now handed out in a balanced (van der Corput) order so any layer count stays spread, not clustered. Still open: motion/rotation defaults, preset import, binaural headphone mode, real-time soft limiter (currently hard-clip), and a CoreAudio channel-label reader.

> **TL;DR** — The Python player (`src/player/src/app/player.py`) sounds drier, "noisier", and obviously point-source compared to an older Max/MSP mixer because the Max version ran **IRCAM Spat5** — a professional spatialiser (VBAP / binaural) wrapped in an algorithmic **room reverb**, with the sources slowly orbiting the listener. Our player has **none** of that: it copies the stereo signal across the speakers as *correlated* duplicates, with no reverb, no positioning, and no decorrelation. On top of that, some served assets are lossy **192 kbps MP3** where the Max library was WAV. The fix is a two-stage pipeline: an **offline conditioning pass** (the answer to "make lossy files play nicely") plus a **real-time spatial renderer** with two auto-selected modes — VBAP for a detected speaker ring and a geometry-free **decorrelated upmix** for unknown rigs — fed by a small **FDN reverb**. The player **auto-detects** the output device's channels and infers a layout; no manual speaker configuration is required.

---

## 1. The problem

The player is server-driven and plays **multiple soundscape loops simultaneously** (layered ambiences). It is deployed in the field to a variety of outputs — sometimes a calibrated multi-speaker installation, sometimes whatever stereo or multichannel device is attached.

Compared to the older Max/MSP mixer, listeners report two distinct issues:

1. **Spatial** — "it feels quite obvious where the sound is coming from"; each source seems pinned to a speaker, rather than the Max version's sensation of *being surrounded* by the sound.
2. **Fidelity** — the Python output "feels more noisy" and lower-fidelity; the Max output feels "less noisy and higher fidelity."

These are two different root causes (spatial rendering and source fidelity) that happen to push perception in the same direction. Both are addressed below.

---

## 2. How the current Python player works

`SoundDevicePlayer` (`src/player/src/app/player.py`) opens a single `sounddevice.OutputStream` at a fixed `fs = 44100`, `dtype="float32"`, and mixes in the real-time callback:

- **Queue / transition model** — `queue_sound()` stages tracks; `dequeue_cosound()` loads files (off the audio thread) and cross-fades old tracks out / new tracks in over `fade_time_ms`. Looping is per-track via a modulo read pointer. *(This part is sound and worth keeping.)*
- **Mixing** — `_audio_callback` (`player.py:135-189`) sums each active track with a per-track gain ramp, applies `channel_gains`, `master_gain`, and clips to [-1, 1].
- **The spatial weakness** — `_adapt_channels_for_output` (`player.py:248-281`) maps an input file to the output channel count:
  - **mono → every output channel** at full gain (`np.repeat`, `player.py:255-256`),
  - **stereo → L into all even-indexed channels, R into all odd-indexed channels**, each scaled by `1/√(count)` (`player.py:263-275`).

The decisive fact: **every speaker in a group receives an *identical* (fully correlated) copy of the same channel.** There is no per-source position, no decorrelation, and no reverberation anywhere in the signal path.

**Two secondary gaps:**

- **Sample rate** — the stream is hardcoded to 44.1 kHz but files are read with no resampling. Any non-44.1 kHz asset plays at the wrong pitch/speed. (The local CoreAudio devices default to **48 kHz** — see §8.)
- **Source fidelity** — the asset cache mixes formats: `assets/2`, `assets/3` are **MPEG layer III, 192 kbps, joint-stereo**; `assets/12`, `assets/13` are WAV. The Max "AAS Loop Library" was all WAV.

---

## 3. The Max/MSP reference implementation (AAS-Mixer)

Located in `.old/maxmsp_impl/`. It is a *different* project (different feature set, not server-driven), but the **playback core is directly comparable** — except the Max mixer typically played one source at a time, where ours layers many.

**Files of record** (added after the initial investigation):

- `Greg_s Mixer Module (v2.1 and later)/AAS-Mixer v2.2 / v2.3 / v2.3.1 / _MSL.maxpat` — the editable patch sources.
- `AAS Mixer Presets/` — concrete scene recipes (parameter values that sound good).
- `MSL 1.1.2.maxpat`, `mira.dataCollect*.maxpat` — the Spat-based data-collection variants.
- `AAS-Mixer v2.3.app` — the compiled standalone (bundles the `spat5.*.mxo` externals).
- `*.docx` — dev logs, changelog, manual.

### 3.1 DSP architecture (recovered from the patch sources)

The engine is **IRCAM Spat5**. Key objects/messages extracted from `AAS-Mixer v2.3.maxpat`:

| Element | Evidence (from patch) | Meaning |
| --- | --- | --- |
| Spatialiser | `spat5.spat~ @inputs 8 @internals 8 @outputs 8 @initwith "/panning/type vbap3d"` | 8 sources rendered by **VBAP3D** across an 8-speaker rig |
| Headphone mode | `spat5.spat~ @inputs 8 @outputs 2 @initwith "/panning/type binaural"` | **Binaural** (HRTF) render for headphones |
| Source layout | `/source/N/aed 129. 0. 3.` (×8) | 8 sources in **Azimuth / Elevation / Distance**; spread 45° apart (`+ 45.`), elev 0, dist 1–3 m |
| Speakers | `spat5.oper @initwith "/source/number 8"`; MSL: `/speaker/number 8` | Spat's **default 8-speaker ring** (positions held in the Spat GUI object) |
| Motion | `sel Static Clockwise Counterclockwise Random-drift`, `metro` + `counter` rotating `/sources/az …` | Slow rotation of the whole sound field, with a speed dial |
| Reverb | `/room/1/reverb/roomsize`, `/room/1/reverberance`, `/room/1/mute` | Spat **algorithmic room reverb**, dial-smoothed with a safety limiter |
| Output | `dac~ 1 2 3 4 5 6 7 8 9 10` | 8 main channels **+ 2 subs** (8.2); 41.2 Hz sub test pulse |

**Concrete "good" values** decoded from a standalone preset (`AAS Mixer Presets/Old presets (for standalone ONLY)/Forest Dawn`, header order = `reverbOn roomSize reverbAmount motionSpeed motionType …`):

```text
1   2020   41.007   5   Counterclockwise   <then 4 layered sources w/ per-panel volume + 5-band EQ>
```

→ reverb **ON**, room ≈ **2020**, reverberance ≈ **41 %**, slow **counterclockwise** rotation, four simultaneous layers. Other presets land at room ≈ 2020–2040, reverberance ≈ 41–65 %.

### 3.2 What Spat5 does conceptually

- **Positional panning** (VBAP/HOA/binaural): each source is a virtual point; only the 2–3 nearest speakers are driven, with gains computed from the source's angle relative to the speaker geometry.
- **Algorithmic room reverb** (feedback-delay-network family): adds early reflections + a diffuse decorrelated late field, sprayed across all outputs.
- **Decorrelation**: inherent to the multi-internal-channel render and the reverb — different speakers get *different* signals.

---

## 4. Why the Max version sounds better — the comparison

| Symptom in Python | Cause in Python | What Max does instead |
| --- | --- | --- |
| "Obvious which speaker" / not enveloping | `_adapt_channels_for_output` sends **identical correlated copies** to many speakers (mono → all). The image collapses to the nearest speaker (precedence/Haas effect); no envelopment. | VBAP drives only the speakers *around each source's position*; decorrelated reverb fills all speakers → a stable, enveloping field. |
| "Noisy / harsh / phasey" | Correlated copies from multiple speakers **comb-filter** at the listening position (frequency-dependent cancellation) → hollow, harsh coloration. | Decorrelated signals don't comb; the reverb's diffuse field smooths the sound. |
| "Lower fidelity" | (a) Fully **dry** signal exposes the raw noise floor and any artifacts; (b) some sources are **192 kbps MP3**, whose artifacts (HF "swirl", pre-echo, stereo-image collapse) are audible on broadband ambient textures (water/wind/insects). | Reverb wash masks/smooths source artifacts; the Max library is **WAV**. |

**The crux:** correlated multi-speaker duplication is the *opposite* of spatialisation. It is what produces both the "point-source" collapse and the comb-filter "noise" simultaneously. Spat5 replaces it with positioned, decorrelated, reverberant rendering.

---

## 5. Requirements & constraints

Derived from the brief:

1. **Lossy-tolerant (hard requirement).** The system must make even 192 kbps MP3 sources sound as good as possible. **Post-processing after download is explicitly acceptable.**
2. **Simultaneous layers.** Multiple soundscapes play at once (unlike the one-at-a-time Max mixer).
3. **Two playback targets:**
   - **Multi-speaker rig** → true positional rendering (**VBAP**).
   - **Arbitrary / unknown speakers** → a robust geometry-free **decorrelated upmix**.
4. **Zero-config / auto-detect.** When no speaker angles or channel data are supplied, the player must **programmatically determine the available speakers** and configure itself.
5. **Honest hardware limit.** The audio stack exposes **channel count, device name, and default sample rate — but not physical speaker angles** (see §8). Auto-detection works within that limit.

---

## 6. Proposed solution — a two-stage pipeline

```text
DOWNLOAD ─► [Stage 1: OFFLINE CONDITIONING] ─► cached clean float WAV ─┐
                                                                       │
STARTUP  ─► [device auto-detect ─► layout inference ─► mode select]    │
                                                                       ▼
PLAYBACK ─► [Stage 2: REAL-TIME RENDER: position → decorrelate → reverb → subs → master]
```

### Stage 1 — Offline conditioning (the lossy-files answer)

Runs once per asset, after download; result is cached as float WAV/FLAC + a sidecar JSON (loudness, true-peak, loop points). Idempotent, keyed by source hash. The real-time player only ever reads conditioned files.

1. **Decode + cache** MP3 → 32-bit float PCM once (never re-decode per play).
2. **Resample to the engine rate** with a high-quality resampler (`soxr`). Fixes the wrong-pitch bug for non-44.1 kHz files.
3. **Loudness-normalise** to a target (EBU R128 / ITU-R BS.1770, e.g. **−20 LUFS**) + **true-peak limit to −1 dBTP**. Automates the Max "balance all volumes" so layers sit together predictably and never inter-sample clip.
4. **Loop-seam repair** — trim MP3 encoder/decoder delay+padding and apply a short equal-power crossfade so random-start loops don't click.
5. **Tame lossy "fizz"** — a gentle high-shelf cut (≈ −2 to −4 dB above ~14–16 kHz); that top octave is where 192 kbps artifacts live on broadband ambient material. Optional conservative spectral denoise for hiss-type sources.

### Stage 2 — Real-time spatial render

Replaces the `_adapt_channels_for_output` block in the callback; keeps the existing queue / fade / mute logic.

- **`SpatialRenderer` (strategy interface)** with two implementations:
  - **`VBAPRenderer`** (detected/known ring): each track holds a position; pairwise VBAP gains across the speaker ring; supports slow rotation (Static / CW / CCW / drift); reverb sent **decorrelated** to all speakers; sub/LFE channels receive a summed low-passed send (crossover ~80–120 Hz).
  - **`DecorrelatedUpmixRenderer`** (unknown N channels): spreads each source across all channels with **per-channel all-pass decorrelation** so the copies are *not* identical. Enveloping on any channel count, **no geometry required**. This is the direct replacement for today's correlated copy.
- **`reverb.py`** — a compact numpy **feedback-delay-network (FDN)** reverb, multi-output with **decorrelated taps per channel**. This is the single biggest contributor to envelopment *and* it masks residual lossy artifacts. Parameters (room size, amount, decay) seeded from the Max presets (§3.1).

---

## 7. Device auto-detection & layout inference

**What is programmatically knowable** (verified by probing `sounddevice` on this machine — the per-device keys are `name, index, hostapi, max_input_channels, max_output_channels, default_low/high_latency, default_samplerate`):

| Property | Reliability | Source |
| --- | --- | --- |
| **Channel count** | ✅ Always | `max_output_channels`. The field rig appears as an **Aggregate / Multi-Output Device** whose channel count we read directly. |
| Default sample rate | ✅ Always | `default_samplerate` (drives Stage 1 resample target). |
| Channel **labels / LFE** (L/R/C/LFE/Ls/Rs…) | ⚠️ Best-effort, macOS only | CoreAudio `AudioChannelLayout` via `ctypes` — **PortAudio drops this**; many pro interfaces report nothing. |
| **Physical speaker angles** | ❌ Not knowable | No OS API exposes true angles. Only via manual override or mic calibration (out of scope). |

**Inference policy** — `devices.py` (probe) + `layout.py` (infer), run at startup, zero manual input:

```text
count → layout:
   1 → mono (0°)
   2 → decorrelated stereo (headphones/AirPods: two front speakers can't
       place full-circle sources, so VBAP is skipped to avoid an L/R snap)
   4 → quad (±45°, ±135°)
   6 → 5.1 (L/R/C/LFE/Ls/Rs, ITU angles)
   8 → even 8-ring @ 45°   (the AAS soundscape default; overridable to 7.1)
   N → even ring @ 360/N°
refine with CoreAudio labels when present (esp. LFE → sub send)
```

**Mode auto-selection** (ties the two targets together so nothing is required from the operator):

- **Confident** (count matches a standard layout, or labels present) → **VBAP** on the inferred ring.
- **Unsure** (unusual count, no labels) → **DecorrelatedUpmix** across whatever channels exist.
- A config file may **override** anything (real angles, sub channels, forced mode) for the calibrated installation, but it is optional.

---

## 8. File / module plan

**New modules** (`src/player/src/app/`):

| File | Responsibility |
| --- | --- |
| `conditioning.py` | Stage 1 offline pass + cache + sidecar metadata |
| `devices.py` | Probe outputs; best-effort CoreAudio channel labels |
| `layout.py` | Infer speaker layout + confidence; choose render mode |
| `spatial.py` | `SpatialRenderer` ABC + `VBAPRenderer` + `DecorrelatedUpmixRenderer` |
| `reverb.py` | Multi-output FDN reverb with decorrelated taps |

**Modified:**

- `player.py` — swap the channel-copy block for `renderer.render(...) → sum → reverb → subs → master → clip`; read mode/layout/reverb params from config; assign positions to tracks.
- `cosound.json` (or a new `audio.json`) — optional overrides: `playback_mode`, `speaker_layout`, sub channels, reverb defaults, rotation, LUFS target.
- `pyproject.toml` — add dependencies.

**Dependencies:** `soxr` (resample), `pyloudnorm` (LUFS), `pedalboard` (JUCE-backed reverb / limiter / shelf EQ / MP3 IO) — or `scipy` for the filters. *(Note: MP3 decoding needs a recent libsndfile or an `ffmpeg`/`pedalboard` fallback.)*

---

## 9. Default parameters (seeded from the Max presets)

| Parameter | Default | Origin |
| --- | --- | --- |
| Engine sample rate | device `default_samplerate` (fallback 48 kHz) | auto-detect |
| Source spread | 8 sources @ 45°, elev 0, dist ~1–3 m | `/source/N/aed`, `+ 45.` |
| Reverb room | ≈ 2020 | preset header |
| Reverb amount | ≈ 41 % (range 0–65 %) | preset header |
| Motion | Static default; CW / CCW / drift available, slow speed | `sel Static …`, speed dial |
| Sub crossover | ~80–120 Hz low-pass to LFE | 8.2 sub handling |
| Loudness target | −20 LUFS, −1 dBTP | conditioning |
| HF de-harsh shelf | −2 to −4 dB above ~14–16 kHz | lossy mitigation |

---

## 10. Rollout phases

1. **Phase 1 — needs no external input, biggest win:** `conditioning.py` + `reverb.py` + `DecorrelatedUpmixRenderer` + device auto-detection. This alone removes the comb-filter "noise" and the point-source collapse and makes lossy files play nicely.
2. **Phase 2 — VBAP:** `VBAPRenderer` on the auto-detected ring + sub routing.
3. **Phase 3 — parity & polish:** field rotation/motion, preset import from `AAS Mixer Presets/`, config overrides, optional binaural (headphone) mode, optional mic-based angle calibration.

**Validation:** null-test the upmix decorrelation (correlated copies should *not* sum coherently); measure inter-channel correlation before/after; confirm LUFS consistency across the asset set; and A/B listening against the Max app on the same source files.

---

## 11. Risks & open questions

- **CPU budget** — a per-source FDN at blocksize 1024 / 44.1–48 kHz for several simultaneous layers may be heavy in pure numpy. Mitigation: run reverb on a small number of shared *buses* rather than per source; consider `pedalboard`'s native reverb.
- **8-channel ambiguity** — 8 outputs could be a 7.1 layout *or* a plain 8-ring. Default to the even ring (better for diffuse ambient material); allow override.
- **MP3 decode path** — depends on libsndfile version; may require an `ffmpeg`/`pedalboard` fallback decoder.
- **True angles** — auto-detection gives a *reasonable* layout, not the venue's real geometry. The calibrated installation should still be able to supply exact angles via config.
- **Binaural** — the Max app also had a headphone binaural mode; deferred to Phase 3 (needs an HRTF set).

---

## Appendix A — Key evidence

- **Spat instantiations:** `spat5.spat~ @inputs 8 @outputs 8 @internals 8 @initwith "/panning/type vbap3d" @mc 1`; binaural variant `@outputs 2`.
- **Source positions:** `/source/1..8/aed 129. 0. 3.` (and `… 1.`) — AED format.
- **Motion:** `sel Static Clockwise Counterclockwise Random-drift`; azimuth step `+ 45.`; `counter` + `metro`.
- **Reverb OSC:** `/room/1/reverb/roomsize $1`, `/room/1/reverberance $1`, `/room/1/mute $1`.
- **Preset header decode:** `1 2020 41.007 5 Counterclockwise …` = reverbOn / roomSize / reverbAmount / motionSpeed / motionType.
- **Assets:** `assets/2`, `assets/3` = MPEG-1 layer III 192 kbps 44.1 kHz joint-stereo; `assets/12`, `assets/13` = RIFF/WAVE. Library origin = WAV.
- **Device probe (this machine):** host = Core Audio; all current outputs report 2 ch; per-device keys carry **no geometry** — confirming the §7 limit.

## Appendix B — Current code references

- `src/player/src/app/player.py:135` — `_audio_callback` (real-time mix).
- `src/player/src/app/player.py:248-281` — `_adapt_channels_for_output` (the correlated-copy upmix to replace).
- `src/player/src/app/player.py:191-195` — `_default_channel_gains` (ad-hoc channel 7–8 attenuation).
- `src/player/src/app/player.py:31` — hardcoded `fs=44100` (no resample on read).
