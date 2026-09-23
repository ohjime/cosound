# Cosound soundscape engine

`soundscape-mixer.js` is the dependency-free Web Audio engine.
`soundscape-store.js` adapts it to the existing Alpine and HTMX UI.

## Layer data

The existing server shape works without changes:

```js
{
  sound_id: 42,
  sound_file: "/media/sounds/rain.ogg",
  sound_gain: 0.6
}
```

When separate A/B recordings are available, the bridge also accepts:

```js
{
  sound_id: 42,
  sound_file_a: "/media/sounds/rain-a.ogg",
  sound_file_b: "/media/sounds/rain-b.ogg",
  sound_gain: 0.6,
  seamless: false,         // baked into a loop (core/audio.py)

  // How the layer plays in its mix — SoundLayer's columns, saved with it.
  playback_rate: 1,
  stretch: 1.75,           // spacing: a pass comes round every length × this
  second_copy: true,       // copy B, half a period behind A
  repetitions: 1,          // periods per cycle ...
  cycle_rest: 0,           // ... then this many seconds of silence; 0 is endless
  start_delay: 0,          // seconds before the first pass
  phase_step: 0,           // B slips this fraction of a period at each shift
  phase_hold: 4,           // after this many passes,
  phase_hold_alt: 4,       // then this many, alternating
  playback_rate_b: null,   // B's own rate, a second pitch; null is A's
  take_turns: false,       // B only after A has finished, and A after B ...
  turn_gap: 0,             // ... with this many seconds between every turn

  // A new sound's loop check, baked into its file when it is saved.
  trim_start: 0,           // seconds from the head of the file
  trim_end: null,          // seconds from the head; null means "to the end"
  loop_crossfade: 0,       // seconds each repeat overlaps the one before it
  loudness_target: null    // LUFS to match this layer to; null is off
}
```

With one `sound_file`, the engine uses that buffer for both offset schedules.
The timing defaults are the schedule every layer had before timing existed —
two drifting copies, without end — so a layer that carries none plays as it
always did. A `seamless` sound starts as one copy, back to back (the store's
`normalizeUiLayer`); timing a saved mix carries always wins.

## Cycles, delays and phase shifting

Every pass's start is worked out from its number, not kept as a running total
(`_startA` / `_startB`), which is what lets the scheduler, the playheads and the
de-click fades all agree:

- **A**, pass `k`: `t0 + k × period + floor(k / repetitions) × cycle_rest`.
  `t0` is when the voice started plus `start_delay`.
- **B**, only with `second_copy`: A's pass `k`, plus `offsetB`, plus the slip.
  The slip grows by `phase_step × period` after `phase_hold` passes, then after
  `phase_hold_alt` more, alternating; the count runs on passes alone, so a
  shift can land mid-cycle. It wraps inside the period, so B always sounds in
  its own A pass's period and a rest silences both copies. The one pass where
  it comes all the way round is dropped — played, it would start before the
  one ahead of it had finished.

With two copies, no rest and no slip, both reduce to exactly the schedule
every layer had before.

## Settings changes and seeking

A settings change rebuilds the voice, but does not restart it.
`retimeLayer(index, layer)` — what the store's `setTiming` calls — prepares the
replacement and anchors it to where the old voice has got to: the same pass of
A, at the same place in the file. t0 is worked back from that, so a new rate
carries on from the note that was sounding, only at the new pitch. A new
crossfade is heard at the next seam, and a crop that now ends behind the
playhead starts the next pass straight away. The two voices hand over in
`HANDOFF_SECONDS` (40ms). Passes the replacement joins part-way are started
at their offset, with whatever is left of their crossfade envelope, and fade
in over the handoff (`voice.handoff`). While a layer is still waiting out
its start delay it keeps waiting, measured against the new delay. Once it is
playing, the delay changes nothing that can be heard.

`seekLayer(index, position)` does the same with the current pass put at
`position` seconds into the file, clamped into the kept region. The pass count
is kept, so B's slip and the cycle stay where they were. The store's
`seek(index, position)` starts or resumes the mix first, and
`hearSeam(index)` seeks to `SEAM_LEAD_SECONDS` (2s) ahead of where the pass
starts fading into the next. Pressing the trim track's waveform seeks
(`trim-seek`).

`replaceLayer` is still the path for a *different* sound — a library pick, a
new file. It starts the replacement from its first pass and crossfades over
`crossfadeSeconds`. Passing `{ delayStart: true }` restarts it through
`start_delay`.

## Two pitches, overlapping or taking turns

`playback_rate_b` gives B its own tape speed, so a layer alternates between two
pitches. Left null, B plays at A's rate, which is every layer saved before it
existed. Each copy's pass lasts its own length heard, and the period is
spaced from the average of the two.

`take_turns` is for when the two pitches must never sound together. B begins
once A has finished and `turn_gap` seconds have passed, and A comes round the
same gap after B. The period is `A heard + gap + B heard + gap`, and
`offsetB` is `A heard + gap`. The stretch plays no part and B never slips,
since either would put the copies over each other. Nothing is pulled in for
a loop crossfade either: each pass still fades by its envelope, but only
inside its own turn. Without a second copy there is nobody to take turns
with, and the layer plays as one copy.

## Seamless loops

A new sound is checked before it is saved: one copy, spacing 1, nothing held
back, while the artist trims it, crossfades its seam and levels it. The engine
plays that live (the loop crossfade below), and `core/audio.py` bakes the same
fold into the stored file — the tail laid over the head with the same
equal-power curves — so it runs from its end straight back into its start.

Two things keep that join clean in the engine. At spacing 1 the period is the
exact region length rather than rounded to the eighth, which would gap or
overlap every join. And a `seamless` pass whose edge is *not* butted against
the next — a gap from spacing, a rest, a delay, a slip — gets a
`DECLICK_SECONDS` fade on that edge, because a baked loop starts and ends
mid-signal. An unbaked file plays exactly as before.

## Trim and loudness

`trim_start` / `trim_end` crop the file without rewriting it: the region is
handed to `start(when, offset, duration)` on each scheduled source, so cropped
layers still share the engine's decoded-buffer cache. Both schedules play the
same stretch, and the drift period follows the cropped length rather than the
file's. The handles are corrected on the way in — a start past its end, or a
crop left over from a longer file — and the corrected values come back out.

`loudness_target` matches a layer by ITU-R BS.1770-4 integrated loudness
(the measurement EBU R128 is built on), taken over the cropped region and
applied as a factor on that layer's gain node, capped at ±24dB and so the
region's loudest sample stays under `PEAK_CEILING_DB` (-1 dBFS) — the bake's
own ceiling. It is a measurement of how loud the layer *seems*, so two
recordings matched to the same target arrive at the same level from the same
fader position. A new sound is matched to `DEFAULT_LOUDNESS_TARGET` (-20, the
venue player's level too) from its first upload, nudgeable by
`LOUDNESS_NUDGE_LU`.

Both are read back through `layerAnalysis(index)`, which is the only way to
learn a file's length, where its crop settled, how long a crossfade it can hold,
or what it measured:

```js
window.cosoundMixer.layerAnalysis(0);
// { duration, trimStart, trimEnd, loopCrossfade, loopCrossfadeMax, period,
//   loudnessTarget, loudness, loudnessGainDb, loudnessPeakDb, loudnessLimit }
```

`duration` is 0 for a layer with no audio, and `loudness` is null when there was
nothing to read — silence, or a region under the standard's 400ms window.
`loudnessLimit` names the cap that held a layer off its target: `"gain"` for
the ±24dB one, `"peak"` for the ceiling.

## The loop crossfade

`loop_crossfade` is how long each repeat of a layer fades into the next, in
seconds. Zero — where every layer starts — is the hard join the two schedules
always had. Above zero, two things happen at once: the period is pulled in by
the fade, so a pass genuinely overlaps the one before it rather than following
it, and each pass is scheduled through a gain node of its own that rises over
its first `loop_crossfade` seconds and falls over its last.

The envelope is per pass, not per voice, because that is what a crossfade is:
two passes are sounding at the same moment and each has to be somewhere
different in its own fade. The voice's gain node cannot do that — it carries the
fader, the mute and the loudness make-up gain, all of which belong to the whole
layer. The curves are equal power, because the two sides of the seam are
different audio — a region's tail against its own head — so they sum
incoherently and a linear pair would dip about 3dB through the join.

The fade is measured in seconds heard, so a layer at half rate fades for the
seconds that were asked for and not for half of them. `loopCrossfadeMax` is the
ceiling and comes back out with the applied value: a pass cannot fade for longer
than half of itself, and the fade cannot pull the period in past half of what
the stretch asked for. Anything past that snaps, the way a crop handle dragged
past its partner does. A millisecond of hold is kept between the two ramps even
at the ceiling, because an automation event landing exactly on the end of a
value curve is the one case Web Audio implementations disagree about.

## Waveforms

`peaksFor(url, buckets)` summarises a file into the min/max envelope a waveform
is drawn from. It is addressed by url rather than by layer index because it goes
through the engine's decoded-buffer cache — a file the mix already plays costs
no fetch and no decode, and one it does not is shared with the voice that
follows. Both the buffer and the envelope are memoised.

```js
await window.cosoundMixer.peaksFor("/media/sounds/rain.ogg");
// { min: Float32Array, max: Float32Array, peak, length }
```

A crop does not invalidate an envelope — `trim-track.js` draws the whole file
and shades what is cut — so unlike a loudness reading it survives every rebuild
of the voice. `peaksFromBuffer(buffer, buckets)` is the same walk over a buffer
you already hold.

## Playheads

`layerPlayheads(index)` says where a layer is sounding, in seconds into its file
— the axis the crop handles are on, so the answers draw straight onto a
waveform.

```js
window.cosoundMixer.layerPlayheads(0);   // [] | [a] | [a, b] | up to four
```

There is no single playhead to return. A voice runs two schedules of the same
crop and spacing them apart is exactly what `stretch` does, so a layer has two
heads, one, or none — between passes the drift is a gap, not a loop, and nothing
is sounding at all. Only passes genuinely in their region are reported.

A schedule can also be sounding twice over: a loop crossfade pulls each pass
into the one before it, and so does a stretch under 1. Four heads is therefore
the ceiling, and mid-crossfade is when it happens — one head running out the
tail while the other comes in at the head.

Positions come off the schedule rather than a clock of their own, so they stay
true across a pause: suspending the context stops `currentTime`, and the heads
stop with it.

## The trim track

`trim-track.js` is the loop check's crop UI: the waveform, a start and an end marker
dragged over it, and the playheads sweeping through. It is registered as the
`trimTrack` Alpine component and used as a bare div — it builds its own canvas,
markers and labels:

```html
<div x-data="trimTrack()"
     x-effect="load({ src, duration, start, end, index, gainDb })"
     @trim-commit="retime($event.detail)"></div>
```

`index` is the voice to ask for playheads, and may be left out when there is no
mix running. `gainDb` is the layer's loudness make-up gain, and it is a vertical
scale on the wave: the base scale normalises to the file's own peak, so an
unmatched layer fills the panel whatever it was recorded at, and the make-up
gain rides on top of that. That is not cosmetic — the make-up gain is a factor
the engine puts on the voice's gain node, so it really is the amplitude coming
out, and dragging the loudness target grows or shrinks the wave live. The fader
deliberately does *not* feed in: it decides how a layer sits against the others,
which is the card's business, not a picture of one layer.

`load` is the whole input and `trim-commit` — `{ trim_start, trim_end }`, fired
on release so a drag costs one rebuild — the whole output. Driving it from
`x-effect` is what keeps it on the layer being edited: the effect re-runs
whenever any store value it read changed, so a corrected crop coming back out of
`layerAnalysis` moves the marker. An end marker at the tail commits
`trim_end: null`, the same "to the end" the rest of the pipeline carries.

## Alpine API

The existing `$store.soundLayers` API remains available. Audio-aware additions:

```js
await Alpine.store("soundLayers").replaceLayer(index, layer);
await Alpine.store("soundLayers").loadMix(mix);
await Alpine.store("soundLayers").playAll();
await Alpine.store("soundLayers").pause();
await Alpine.store("soundLayers").resume();

// Every timing setting, the crossfade and the crop all rebuild the voice, so
// they share one setter. The layer carries on from where it was.
await Alpine.store("soundLayers").setTiming(index, { trim_start: 4, trim_end: 30 });
await Alpine.store("soundLayers").setTiming(index, { loop_crossfade: 2.5 });
await Alpine.store("soundLayers").setTiming(index, { cycle_rest: 20, repetitions: 3 });
// Loudness does not: pass a target in LUFS, or null to switch it off.
Alpine.store("soundLayers").setLoudness(index, -23);
// Play one layer from 12s into its file, or from just before its seam.
await Alpine.store("soundLayers").seek(index, 12);
await Alpine.store("soundLayers").hearSeam(index);
```

Each of those writes `duration`, `trim_start`, `trim_end`, `loop_crossfade`,
`loop_crossfade_max`, `period`, `loudness`, `loudness_gain_db`,
`loudness_peak_db` and `loudness_limit` back onto the layer, so a template can
render a crop slider, a crossfade slider already sized to its ceiling, and a
reading straight off the layer (see `cotton/core_sound_layer_settings.html`).

## HTMX / DOM event API

Any swapped HTMX fragment can request audio changes without importing a module:

```js
document.dispatchEvent(new CustomEvent("cosound:audio:replace-request", {
  detail: { index: 2, layer: serverLayer }
}));

document.dispatchEvent(new CustomEvent("cosound:audio:gain-request", {
  detail: { index: 2, value: 0.65 }
}));

document.dispatchEvent(new Event("cosound:audio:play"));
document.dispatchEvent(new Event("cosound:audio:pause"));
document.dispatchEvent(new Event("cosound:audio:resume"));
```

The bridge emits:

- `cosound:audio:progress`
- `cosound:audio:ready`
- `cosound:audio:replace`
- `cosound:audio:mixload`
- `cosound:audio:timing`
- `cosound:audio:loudness`
- `cosound:audio:state`
- `cosound:audio:error`

`window.cosoundMixer` exposes the current `SoundscapeMixer` instance for
advanced controls such as `setStereoWidth()` and `setMasterGain()`.

When HTMX removes an element containing `data-cosound-mixer-root`, the bridge
destroys the old `AudioContext` and scheduled sources automatically.
