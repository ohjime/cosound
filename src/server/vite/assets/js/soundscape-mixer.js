/**
 * A Web Audio soundscape engine inspired by the scheduling pattern used by
 * myNoise. It loads finite files, creates two offset one-shot schedules per
 * layer, and lets the combined layer periods drift instead of looping HTML
 * audio elements in lockstep.
 *
 * This module has no Alpine or HTMX dependency. UI integrations can use the
 * public methods or the DOM event bridge in soundscape-store.js.
 */

export const DEFAULT_STRETCH = 1.75;
export const DEFAULT_LOOK_AHEAD = 0.5;
export const DEFAULT_SCHEDULER_INTERVAL = 100;

/**
 * cosound's house level, where a new sound is levelled before it is saved. It
 * is the venue player's conditioning target too (src/player conditioning.py),
 * so a sound baked here arrives there already where that player would put it.
 * Eight layers stack under one master, which is why this sits well under a
 * streaming target (-14).
 */
export const DEFAULT_LOUDNESS_TARGET = -20;

/** How far an artist may nudge a new sound off the house level, either way. */
export const LOUDNESS_NUDGE_LU = 6;

/**
 * The highest sample peak loudness matching may raise a layer to. A baked
 * file cannot go past full scale without clipping for good, so the audition
 * stops where the bake will (core/audio.py PEAK_CEILING_DBFS) — what the artist
 * hears before saving is what the file holds after.
 */
export const PEAK_CEILING_DB = -1;

/**
 * How long a seamless sound's pass fades at an edge that is not butted against
 * the next one. A baked loop starts and ends mid-signal, so a pass followed by
 * a gap would otherwise stop dead and click. Short enough to be heard only as
 * the click going away.
 */
export const DECLICK_SECONDS = 0.01;

/**
 * How far loudness matching may push a layer, either way. A field recording
 * made at -50 LUFS genuinely needs +27dB to reach -23, but that much make-up
 * gain is all hiss — the cap keeps a quiet source quiet rather than ruining it,
 * and the settings pane shows the applied dB so the shortfall is visible.
 */
export const LOUDNESS_GAIN_LIMIT_DB = 24;

/** The shortest stretch a crop may leave behind. */
export const MIN_REGION_SECONDS = 0.25;

/**
 * How long a layer takes to hand over to a rebuilt voice of itself — a settings
 * change, or a seek (`retimeLayer`). The old voice fades out over this while
 * the new one, already at the same place in the file, fades in: short enough
 * to be heard as the change landing rather than as a fade, long enough not to
 * click.
 */
export const HANDOFF_SECONDS = 0.04;

// How far ahead of `currentTime` a handoff is placed, so the replacement's
// sources are queued before the moment they have to start.
const HANDOFF_LEAD = 0.03;

export function clamp(value, min = 0, max = 1) {
    return Math.max(min, Math.min(max, Number(value) || 0));
}

export function roundToEighth(seconds) {
    return Math.round(Number(seconds) * 8) / 8;
}

export function gainFromSlider(value) {
    return clamp(value) ** 3;
}

function numberOrNull(value) {
    if (value == null || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

/**
 * The slice of a buffer a layer actually plays, from the artist's two crop
 * handles. Both are measured from the head of the file in seconds, and
 * `trimEnd: null` means "to the end" — which is what a layer that has never
 * been cropped carries.
 *
 * This is the only place the handles are interpreted, so it is also the only
 * place they are corrected: the store reads the region back out and writes the
 * corrected numbers onto the layer, so a slider that was dragged past its
 * partner visibly snaps instead of quietly meaning something else.
 */
export function cropRegion(duration, { trimStart = 0, trimEnd = null } = {}) {
    const total = Math.max(0, Number(duration) || 0);
    if (total <= 0) return { offset: 0, duration: 0 };
    const shortest = Math.min(MIN_REGION_SECONDS, total);
    const end = trimEnd == null
        ? total
        : Math.min(total, Math.max(0, Number(trimEnd) || 0));
    const offset = Math.min(
        Math.max(0, Number(trimStart) || 0),
        Math.max(0, end - shortest),
    );
    return { offset, duration: Math.max(shortest, end - offset) };
}

/**
 * When a schedule repeats, and how much of itself each pass overlaps.
 *
 * `loopCrossfade` is the artist's crossfade in seconds: each pass is pulled
 * that much closer to the one before it, so the tail of one repeat sounds over
 * the head of the next instead of butting against it. The fade itself is an
 * envelope per pass — see `_envelope` — and this is where the schedule makes
 * room for it.
 *
 * The ceiling comes back out as `loopCrossfadeMax`, because only this function
 * can work it out and both the panel's slider and the engine need the same
 * number. Two things set it: a pass cannot fade for longer than half of itself
 * (the two ramps would cross), and the crossfade cannot pull the period in past
 * half of what the stretch asked for, which is what stops a short loop with a
 * long fade from scheduling itself into the ground.
 *
 * `playbackRateB` is the second copy's own rate — the layer's second pitch —
 * or null for the first's. Lengths are compared as heard, so a copy played
 * slower takes its longer share of the period.
 *
 * `takeTurns` is the other shape: the copies never overlap. B begins when A
 * has finished and `turnGap` seconds have passed, and A comes round the same
 * gap after B, so the period is both passes and two gaps. The stretch plays
 * no part in it, and nothing is pulled in for the crossfade — pulling in is an
 * overlap, which is what taking turns rules out.
 *
 * A stretch of exactly 1 is back to back, and there the lengths are used as
 * they are. Rounding them to the eighth would leave a baked loop a fraction
 * short of — or past — its own end at every join, which is exactly the seam
 * the bake removed. Everywhere else the rounding stays, so the drift of every
 * mix saved before this is unchanged.
 */
export function timingForBuffers(durationA, durationB, {
    stretch = DEFAULT_STRETCH,
    playbackRate = 1,
    playbackRateB = null,
    loopCrossfade = 0,
    takeTurns = false,
    turnGap = 0,
} = {}) {
    const safeRate = Math.max(0.01, Number(playbackRate) || 1);
    const rateB = playbackRateB == null ? safeRate : Math.max(0.01, Number(playbackRateB) || 1);
    if (takeTurns) {
        const heardA = Math.max(0, Number(durationA) || 0) / safeRate;
        const heardB = Math.max(0, Number(durationB) || 0) / rateB;
        const gap = Math.max(0, Number(turnGap) || 0);
        const loopCrossfadeMax = Math.min(heardA, heardB) / 2;
        return {
            loopCrossfade: Math.min(Math.max(0, Number(loopCrossfade) || 0), loopCrossfadeMax),
            loopCrossfadeMax,
            period: Math.max(0.125, heardA + gap + heardB + gap),
            offsetB: heardA + gap,
        };
    }
    const butted = Math.abs(Number(stretch) - 1) < 1e-9;
    const a = butted ? Math.max(0, Number(durationA) || 0) : roundToEighth(durationA);
    const b = butted ? Math.max(0, Number(durationB) || 0) : roundToEighth(durationB);
    const base = ((a / safeRate + b / rateB) / 2) * stretch;
    const loopCrossfadeMax = Math.max(0, Math.min(Math.min(a / safeRate, b / rateB), base) / 2);
    const fade = Math.min(Math.max(0, Number(loopCrossfade) || 0), loopCrossfadeMax);
    return {
        loopCrossfade: fade,
        loopCrossfadeMax,
        // Floored, because the scheduler advances by one period per iteration:
        // a period of zero — which a hard crop of a very short file rounds down
        // to — would spin `_tick` forever instead of filling the look-ahead.
        period: Math.max(0.125, base - fade),
        // Where B sits inside the cycle is the stretch's business, so the
        // crossfade is not taken off it: pulling both in would slide the two
        // schedules together rather than tightening each one's own loop.
        offsetB: (a / 2) * stretch / safeRate,
    };
}

/**
 * How many phase shifts a schedule has made before pass `k`.
 *
 * A shift comes after `holdX` passes, the next after `holdY` more, then `holdX`
 * again, and so on — the two holds alternate. The count runs on passes alone,
 * so it knows nothing about cycles: a shift can land in the middle of one, and
 * the count carries on through the rest after it.
 */
export function shiftsBefore(k, holdX, holdY) {
    if (!(k > 0)) return 0;
    const x = Math.max(1, Math.round(holdX) || 1);
    const y = Math.max(1, Math.round(holdY) || 1);
    const pairs = Math.floor(k / (x + y));
    return pairs * 2 + (k - pairs * (x + y) >= x ? 1 : 0);
}

function wholeNumber(value, fallback, min = 1) {
    const number = Math.round(Number(value));
    return Number.isFinite(number) ? Math.max(min, number) : fallback;
}

function normalizeLayer(layer, index) {
    const fallbackUrl = layer.sound_file ?? layer.url ?? "";
    return {
        id: layer.sound_id ?? layer.id ?? index,
        urlA: layer.urlA ?? layer.sound_file_a ?? fallbackUrl,
        urlB: layer.urlB ?? layer.sound_file_b ?? fallbackUrl,
        level: clamp(
            layer.level
            ?? (layer.gain != null ? Number(layer.gain) / 100 : undefined)
            ?? layer.sound_gain
            ?? 0.5,
        ),
        muted: Boolean(layer.muted ?? layer.mute),
        solo: Boolean(layer.solo ?? layer.isolated),
        playbackRate: Math.max(0.01, Number(layer.playbackRate ?? 1)),
        // The second copy's own rate, so the layer alternates between two
        // pitches. null plays B at the first's, as every layer always has.
        playbackRateB: (() => {
            const rate = numberOrNull(layer.playbackRateB ?? layer.playback_rate_b);
            return rate == null ? null : Math.max(0.01, rate);
        })(),
        // The copies never overlap: each waits for the other to finish, then
        // `turnGap` seconds. Only means anything with a second copy.
        takeTurns: Boolean(layer.takeTurns ?? layer.take_turns ?? false),
        turnGap: Math.max(0, Number(layer.turnGap ?? layer.turn_gap ?? 0) || 0),
        stretch: Math.max(0.01, Number(layer.stretch ?? DEFAULT_STRETCH)),
        // How long each repeat of this layer fades into the next, in seconds.
        // Zero — where every layer starts — is the hard join the passes had
        // before there was a control for it.
        loopCrossfade: Math.max(
            0,
            Number(layer.loopCrossfade ?? layer.loop_crossfade ?? 0) || 0,
        ),
        trimStart: Math.max(0, Number(layer.trimStart ?? layer.trim_start ?? 0) || 0),
        trimEnd: numberOrNull(layer.trimEnd ?? layer.trim_end),
        // null switches loudness matching off, which is how every layer starts.
        loudnessTarget: numberOrNull(layer.loudnessTarget ?? layer.loudness_target),
        // The second of the two offset copies, B. Every layer has always had
        // one; a seamless sound starts without it, so its loop is heard alone.
        secondCopy: Boolean(layer.secondCopy ?? layer.second_copy ?? true),
        // A file baked into a loop (core/audio.py): it starts and ends
        // mid-signal, so any pass edge that is not butted gets a de-click fade.
        seamless: Boolean(layer.seamless),
        // A cycle is `repetitions` periods followed by `cycleRest` seconds of
        // silence. A rest of 0 is the endless schedule every layer had before.
        repetitions: wholeNumber(layer.repetitions, 1),
        cycleRest: Math.max(0, Number(layer.cycleRest ?? layer.cycle_rest ?? 0) || 0),
        // A wait before the layer's first pass, so layers need not all begin
        // together.
        startDelay: Math.max(0, Number(layer.startDelay ?? layer.start_delay ?? 0) || 0),
        // Phase shifting: B slips `phaseStep` of a period later after
        // `phaseHold` passes, then after `phaseHoldAlt` more, alternating.
        // A step of 0 keeps B where it has always been.
        phaseStep: clamp(Number(layer.phaseStep ?? layer.phase_step ?? 0) || 0, 0, 0.5),
        phaseHold: wholeNumber(layer.phaseHold ?? layer.phase_hold, 4),
        phaseHoldAlt: wholeNumber(layer.phaseHoldAlt ?? layer.phase_hold_alt, 4),
        metadata: layer,
    };
}

/** The highest absolute sample in one region of a buffer, or null unknown. */
export function regionPeak(buffer, { offset = 0, duration = null } = {}) {
    if (typeof buffer?.getChannelData !== "function") return null;
    const sampleRate = Number(buffer.sampleRate) || 48000;
    const channels = Math.max(1, buffer.numberOfChannels || 1);
    const total = buffer.length ?? Math.round((buffer.duration || 0) * sampleRate);
    const start = Math.min(total, Math.max(0, Math.round(offset * sampleRate)));
    const span = duration == null ? total - start : Math.round(duration * sampleRate);
    const end = Math.min(total, start + Math.max(0, span));
    let peak = 0;
    for (let channel = 0; channel < channels; channel += 1) {
        const data = buffer.getChannelData(channel);
        for (let i = start; i < end; i += 1) {
            const value = data[i] < 0 ? -data[i] : data[i];
            if (value > peak) peak = value;
        }
    }
    return peak;
}

// ---------------------------------------------------------------------------
// Loudness, per ITU-R BS.1770-4 (the measurement EBU R128 is built on).
//
// A peak or an RMS reading says nothing useful about how loud a layer *seems*:
// a bright stream and a low rumble can share a peak and sit forty dB apart to
// the ear. BS.1770 fixes that by K-weighting the signal — a shelf that lifts
// the highs the way a head does, then a high-pass that discards the sub-bass no
// one hears as level — and then averaging energy over gated 400ms blocks, so
// the silence between events does not drag the number down.
//
// Everything below is plain arithmetic over the decoded buffer rather than
// Web Audio nodes: this has to run faster than real time on a buffer that is
// not playing, which an OfflineAudioContext render could not promise.
// ---------------------------------------------------------------------------

const ABSOLUTE_GATE_LUFS = -70;
const RELATIVE_GATE_LU = -10;
const BLOCK_STEP_SECONDS = 0.1;
/** BS.1770 channel weights: L, R, C flat; the surrounds lifted by ~1.5dB. */
const CHANNEL_WEIGHTS = [1, 1, 1, 1.41, 1.41];

/**
 * The two K-weighting biquads, derived for whatever rate the file decoded at.
 *
 * The standard prints its coefficients at 48kHz only, and our library is full
 * of 44.1kHz material; using the 48k numbers there would slide both corners
 * about 9% up the spectrum. These are the analog prototypes the 48k table comes
 * from, bilinear-transformed at the actual rate, so 48k reproduces the printed
 * table and every other rate gets the filter the standard meant.
 */
export function kWeightingStages(sampleRate) {
    const rate = Number(sampleRate) > 0 ? Number(sampleRate) : 48000;

    // Stage 1 — high shelf, +4dB above ~1.7kHz (the head's own response).
    const shelfK = Math.tan(Math.PI * 1681.974450955533 / rate);
    const shelfQ = 0.7071752369554196;
    const vh = 10 ** (3.999843853973347 / 20);
    const vb = vh ** 0.4996667741545416;
    const shelfDen = 1 + shelfK / shelfQ + shelfK * shelfK;

    // Stage 2 — RLB high pass, rolling off below ~38Hz.
    const passK = Math.tan(Math.PI * 38.13547087602444 / rate);
    const passQ = 0.5003270373238773;
    const passDen = 1 + passK / passQ + passK * passK;

    return [
        {
            b0: (vh + vb * shelfK / shelfQ + shelfK * shelfK) / shelfDen,
            b1: 2 * (shelfK * shelfK - vh) / shelfDen,
            b2: (vh - vb * shelfK / shelfQ + shelfK * shelfK) / shelfDen,
            a1: 2 * (shelfK * shelfK - 1) / shelfDen,
            a2: (1 - shelfK / shelfQ + shelfK * shelfK) / shelfDen,
        },
        {
            b0: 1,
            b1: -2,
            b2: 1,
            a1: 2 * (passK * passK - 1) / passDen,
            a2: (1 - passK / passQ + passK * passK) / passDen,
        },
    ];
}

/** Direct-form-I biquad, run over the samples in place. */
function filterInPlace(samples, { b0, b1, b2, a1, a2 }) {
    let x1 = 0;
    let x2 = 0;
    let y1 = 0;
    let y2 = 0;
    for (let i = 0; i < samples.length; i += 1) {
        const x0 = samples[i];
        const y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
        samples[i] = y0;
        x2 = x1;
        x1 = x0;
        y2 = y1;
        y1 = y0;
    }
}

function blockLoudness(meanSquare) {
    return -0.691 + 10 * Math.log10(meanSquare);
}

/**
 * The integrated loudness of one region of a buffer, in LUFS.
 *
 * Returns -Infinity when there is nothing to measure — silence, or a region
 * shorter than the standard's 400ms window. Callers read that as "no reading",
 * not as "very quiet", and leave the layer's gain alone.
 *
 * Synchronous, and around 60ms for a minute of stereo audio. That is a hitch
 * the artist pays once, on the click that switches loudness matching on for a
 * layer: the caller caches the reading against the file and the region it was
 * taken over, so moving the target afterwards costs a subtraction.
 *
 * @param {AudioBuffer} buffer
 * @param {{offset?: number, duration?: number|null}} [region]
 */
export function measureLoudness(buffer, { offset = 0, duration = null } = {}) {
    if (typeof buffer?.getChannelData !== "function") return -Infinity;
    const sampleRate = Number(buffer.sampleRate) || 48000;
    const channels = Math.max(1, buffer.numberOfChannels || 1);
    const total = buffer.length ?? Math.round((buffer.duration || 0) * sampleRate);
    const start = Math.min(total, Math.max(0, Math.round(offset * sampleRate)));
    const span = duration == null ? total - start : Math.round(duration * sampleRate);
    const length = Math.max(0, Math.min(total - start, span));

    // 400ms windows overlapping by 75%. Sizing the window as exactly four steps
    // (rather than rounding 400ms separately) is what lets a block be the sum of
    // four consecutive step sums, so the whole region is squared once instead of
    // four times over.
    const step = Math.max(1, Math.round(BLOCK_STEP_SECONDS * sampleRate));
    const blockSize = step * 4;
    if (length < blockSize) return -Infinity;

    const stages = kWeightingStages(sampleRate);
    const steps = Math.floor(length / step);
    const blocks = steps - 3;
    // Each entry is the block's weighted mean square, summed across channels.
    const meanSquares = new Float64Array(blocks);

    for (let channel = 0; channel < channels; channel += 1) {
        const weight = CHANNEL_WEIGHTS[channel] ?? 1;
        const samples = Float64Array.from(
            buffer.getChannelData(channel).subarray(start, start + length),
        );
        for (const stage of stages) filterInPlace(samples, stage);

        const stepEnergy = new Float64Array(steps);
        for (let s = 0; s < steps; s += 1) {
            let sum = 0;
            const from = s * step;
            for (let i = from; i < from + step; i += 1) sum += samples[i] * samples[i];
            stepEnergy[s] = sum;
        }
        for (let b = 0; b < blocks; b += 1) {
            const energy = stepEnergy[b] + stepEnergy[b + 1]
                + stepEnergy[b + 2] + stepEnergy[b + 3];
            meanSquares[b] += weight * (energy / blockSize);
        }
    }

    // Two-stage gate: drop everything below -70 LUFS outright, then drop
    // everything more than 10 LU under what is left. Without it, the pauses in
    // a sparse recording would count as programme material.
    const audible = [];
    for (const meanSquare of meanSquares) {
        if (blockLoudness(meanSquare) > ABSOLUTE_GATE_LUFS) audible.push(meanSquare);
    }
    if (!audible.length) return -Infinity;

    const mean = (values) => values.reduce((a, b) => a + b, 0) / values.length;
    const relativeGate = blockLoudness(mean(audible)) + RELATIVE_GATE_LU;
    const gated = audible.filter((ms) => blockLoudness(ms) > relativeGate);
    if (!gated.length) return -Infinity;
    return blockLoudness(mean(gated));
}

/**
 * How much to lift or drop a layer to land it on its target, in dB, capped
 * both ways by LOUDNESS_GAIN_LIMIT_DB. Zero whenever there is nothing to go on.
 */
export function loudnessGainDb(measured, target, limit = LOUDNESS_GAIN_LIMIT_DB) {
    if (target == null || !Number.isFinite(measured)) return 0;
    return Math.max(-limit, Math.min(limit, Number(target) - measured));
}

// ---------------------------------------------------------------------------
// Waveform envelope.
//
// A drawable summary of a file: the lowest and highest sample in each of
// `buckets` equal slices of it, which is what a waveform actually is. It is
// taken here rather than in the drawing code because the decoded buffers live
// here — peaksFor goes through the same cache the voices load from, so drawing
// a layer the mix already plays costs no fetch and no second decode.
//
// Resolution is deliberately higher than any panel is wide. The envelope is
// computed once per file and the renderer folds it down to however many bars it
// has room for, so a resize redraws without coming back here.
// ---------------------------------------------------------------------------

export const DEFAULT_PEAK_BUCKETS = 2048;

// How many passes back a playhead is looked for. A stretch at its floor with
// the crossfade at its ceiling overlaps four passes of one copy; one more
// covers B, which trails the A pass it belongs to by up to a period.
const PLAYHEAD_LOOKBACK = 5;

// Longest run of samples one bucket will look at, per channel. Past this the
// bucket is subsampled: an envelope is min/max over tens of thousands of
// samples of an oscillating signal, and every stride hits the same extremes
// within a pixel. Without the cap a ten-minute file would walk ~30M samples on
// the main thread to draw ~800 bars.
const PEAK_SAMPLE_LIMIT = 4096;

/**
 * @param   {AudioBuffer} buffer
 * @param   {number}      [buckets] columns to summarise the file into
 * @returns {{min: Float32Array, max: Float32Array, peak: number, length: number}}
 */
export function peaksFromBuffer(buffer, buckets = DEFAULT_PEAK_BUCKETS) {
    const length = Math.max(1, Math.floor(buckets));
    const min = new Float32Array(length);
    const max = new Float32Array(length);
    const empty = { min, max, peak: 0, length };
    if (typeof buffer?.getChannelData !== "function") return empty;
    const samples = buffer.length
        ?? Math.round((buffer.duration || 0) * (buffer.sampleRate || 0));
    if (!samples) return empty;

    const channels = Math.max(1, buffer.numberOfChannels || 1);
    let peak = 0;
    for (let channel = 0; channel < channels; channel += 1) {
        const data = buffer.getChannelData(channel);
        for (let bucket = 0; bucket < length; bucket += 1) {
            const from = Math.floor((bucket * samples) / length);
            const to = Math.min(
                samples,
                Math.max(from + 1, Math.floor(((bucket + 1) * samples) / length)),
            );
            const stride = Math.max(1, Math.ceil((to - from) / PEAK_SAMPLE_LIMIT));
            let low = min[bucket];
            let high = max[bucket];
            for (let i = from; i < to; i += stride) {
                const value = data[i];
                if (value < low) low = value;
                if (value > high) high = value;
            }
            min[bucket] = low;
            max[bucket] = high;
            if (-low > peak) peak = -low;
            if (high > peak) peak = high;
        }
    }
    return { min, max, peak, length };
}

// ---------------------------------------------------------------------------
// Loop crossfade curves.
//
// Equal power rather than linear, because the two sides of a loop's seam are
// different audio — the tail of the region against its own head — so they sum
// incoherently and a pair of straight lines would dip about 3dB through the
// join, which is the hole a crossfade is there to avoid.
//
// Sampled once and shared: setValueCurveAtTime stretches whatever curve it is
// given over the duration it is given, so one pair of arrays serves every pass
// of every layer at every fade length.
// ---------------------------------------------------------------------------

function equalPowerCurve(rising, points = 128) {
    const curve = new Float32Array(points);
    for (let i = 0; i < points; i += 1) {
        const phase = (i / (points - 1)) * (Math.PI / 2);
        curve[i] = rising ? Math.sin(phase) : Math.cos(phase);
    }
    return curve;
}

const FADE_IN = equalPowerCurve(true);
const FADE_OUT = equalPowerCurve(false);

/**
 * The rest of an equal-power curve from `fraction` of the way along it, for a
 * pass that joins its crossfade part-way — one a handoff starts mid-pass. A
 * value curve cannot start in the past (it would be clamped to now and play
 * the whole curve late), so the part still to come is sampled as a curve of
 * its own.
 */
function remainingCurve(rising, fraction, points = 64) {
    const from = clamp(fraction) * (Math.PI / 2);
    const curve = new Float32Array(points);
    for (let i = 0; i < points; i += 1) {
        const phase = from + (i / (points - 1)) * (Math.PI / 2 - from);
        curve[i] = rising ? Math.sin(phase) : Math.cos(phase);
    }
    return curve;
}

function stopSources(voice, when = 0) {
    for (const source of voice.activeSources) {
        try {
            source.stop(when);
        } catch {
            // The source may already have ended.
        }
    }
    voice.activeSources.clear();
}

/**
 * Thrown by a load that was still decoding when the mixer was destroyed.
 *
 * Decoding is the slow part of preparing a voice, and it is exactly where a
 * mixer gets torn down: HTMX swaps the card out, or the store starts a fresh
 * load over the top. By the time the files arrive the AudioContext is closed,
 * so building the voice's gain node on it would only earn a console warning
 * per layer. The load stops instead, and its caller can tell this apart from
 * a file that genuinely failed.
 */
export class MixerDestroyedError extends Error {
    constructor() {
        super("The mixer was destroyed while it was loading.");
        this.name = "MixerDestroyedError";
    }
}

export class SoundscapeMixer extends EventTarget {
    constructor({
        audioContext,
        lookAhead = DEFAULT_LOOK_AHEAD,
        schedulerInterval = DEFAULT_SCHEDULER_INTERVAL,
        masterGain = 0.5,
        stereoWidth = 1,
        crossfadeSeconds = 1.8,
    } = {}) {
        super();
        const AudioContextClass = globalThis.AudioContext ?? globalThis.webkitAudioContext;
        if (!audioContext && !AudioContextClass) {
            throw new Error("This browser does not support the Web Audio API.");
        }

        this.context = audioContext ?? new AudioContextClass();
        this.lookAhead = lookAhead;
        this.schedulerInterval = schedulerInterval;
        this.crossfadeSeconds = crossfadeSeconds;
        this.voices = [];
        this.started = false;
        this.destroyed = false;
        this._timer = null;
        this._bufferCache = new Map();
        // Keyed by url and crop region, because a reading depends on both and
        // on nothing else. Re-preparing a voice is common — every rate, stretch
        // or crop change rebuilds one — and only a crop invalidates the reading,
        // so the target slider and the rate slider both come back for free.
        this._loudnessCache = new Map();
        // Keyed by url and bucket count. A crop does not invalidate a waveform —
        // the trim UI draws the whole file and shades what is cut — so unlike
        // the loudness cache this survives every rebuild of the voice.
        this._peaksCache = new Map();
        this._buildMasterGraph(masterGain, stereoWidth);
    }

    _buildMasterGraph(masterGain, stereoWidth) {
        const context = this.context;
        this.input = context.createGain();
        this.splitter = context.createChannelSplitter(2);
        this.merger = context.createChannelMerger(2);
        this.master = context.createGain();
        this.limiter = context.createDynamicsCompressor();

        // Matrix stereo-width processor:
        // L' = ((1+w)/2)L + ((1-w)/2)R
        // R' = ((1-w)/2)L + ((1+w)/2)R
        this.matrix = {
            leftToLeft: context.createGain(),
            rightToLeft: context.createGain(),
            leftToRight: context.createGain(),
            rightToRight: context.createGain(),
        };

        this.input.connect(this.splitter);
        this.splitter.connect(this.matrix.leftToLeft, 0);
        this.splitter.connect(this.matrix.leftToRight, 0);
        this.splitter.connect(this.matrix.rightToLeft, 1);
        this.splitter.connect(this.matrix.rightToRight, 1);
        this.matrix.leftToLeft.connect(this.merger, 0, 0);
        this.matrix.rightToLeft.connect(this.merger, 0, 0);
        this.matrix.leftToRight.connect(this.merger, 0, 1);
        this.matrix.rightToRight.connect(this.merger, 0, 1);
        this.merger.connect(this.master).connect(this.limiter).connect(context.destination);

        this.master.gain.value = clamp(masterGain);
        this.limiter.threshold.value = -12;
        this.limiter.knee.value = 6;
        this.limiter.ratio.value = 10;
        this.limiter.attack.value = 0.05;
        // Some browsers cap this AudioParam at 1 second.
        const maximumRelease = Number.isFinite(this.limiter.release.maxValue)
            ? this.limiter.release.maxValue
            : 1;
        this.limiter.release.value = Math.min(2, maximumRelease);
        this.setStereoWidth(stereoWidth);
    }

    setStereoWidth(width) {
        const w = clamp(width, 0, 1.8);
        const direct = (1 + w) / 2;
        const cross = (1 - w) / 2;
        const now = this.context.currentTime;
        this.matrix.leftToLeft.gain.setTargetAtTime(direct, now, 0.03);
        this.matrix.rightToRight.gain.setTargetAtTime(direct, now, 0.03);
        this.matrix.rightToLeft.gain.setTargetAtTime(cross, now, 0.03);
        this.matrix.leftToRight.gain.setTargetAtTime(cross, now, 0.03);
    }

    setMasterGain(value) {
        this.master.gain.setTargetAtTime(clamp(value), this.context.currentTime, 0.05);
    }

    async _decode(url) {
        if (!url) throw new Error("A soundscape layer is missing an audio URL.");
        if (!this._bufferCache.has(url)) {
            const promise = fetch(url, { credentials: "same-origin" })
                .then((response) => {
                    if (!response.ok) {
                        throw new Error(`Could not load ${url} (${response.status}).`);
                    }
                    return response.arrayBuffer();
                })
                .then((data) => this.context.decodeAudioData(data));
            this._bufferCache.set(url, promise);
        }
        try {
            return await this._bufferCache.get(url);
        } catch (error) {
            this._bufferCache.delete(url);
            throw error;
        }
    }

    /**
     * A second of silence, used for a layer that has no audio yet.
     *
     * The `+` button makes room for a layer to be filled in later. That layer
     * still has to own a voice, because the store addresses layers by
     * index — skipping it here would shift every voice after it out from under
     * its fader. A silent voice keeps the mapping honest and costs nothing.
     */
    _silence() {
        const rate = this.context.sampleRate || 44100;
        return this.context.createBuffer(2, rate, rate);
    }

    _throwIfDestroyed() {
        if (this.destroyed) throw new MixerDestroyedError();
    }

    async _prepareVoice(layer, index, onFileLoaded) {
        const config = normalizeLayer(layer, index);
        const bufferA = config.urlA ? await this._decode(config.urlA) : this._silence();
        this._throwIfDestroyed();
        onFileLoaded?.();
        const bufferB = config.urlB === config.urlA
            ? bufferA
            : await this._decode(config.urlB);
        this._throwIfDestroyed();
        if (config.urlB !== config.urlA) onFileLoaded?.();

        const gain = this.context.createGain();
        gain.gain.value = 0;
        gain.connect(this.input);
        // The crop applies to both passes — it belongs to the track, not to one
        // schedule — and the period follows the cropped length, so trimming a
        // long tail tightens the drift instead of leaving a silent gap where
        // the tail used to be.
        const region = cropRegion(bufferA.duration, config);
        const regionB = cropRegion(bufferB.duration, config);
        const timing = timingForBuffers(region.duration, regionB.duration, {
            ...config,
            takeTurns: config.secondCopy && config.takeTurns,
        });
        const voice = {
            config,
            bufferA,
            bufferB,
            gain,
            region,
            regionB,
            loudness: null,
            loudnessGainDb: 0,
            loudnessGain: 1,
            // The crossfade as the schedule could actually take it, and the
            // most it would have taken. The panel's slider reads both back
            // through layerAnalysis, so a fade asked for past the ceiling snaps
            // to it the same way a crop handle does.
            loopCrossfade: timing.loopCrossfade,
            loopCrossfadeMax: timing.loopCrossfadeMax,
            period: timing.period,
            offsetB: timing.offsetB,
            // Where pass 0 of A begins, and the next pass of each copy still
            // to be scheduled. Every pass's start is worked out from these
            // (_startA / _startB) rather than kept as a running total, which
            // is what lets a rest, a slip and a playhead all agree on it.
            t0: 0,
            passA: 0,
            passB: 0,
            // When this voice took over from the one before it (retimeLayer).
            // A pass that began before then is joined part-way, from where it
            // has got to, rather than played from its head.
            handoff: -Infinity,
            activeSources: new Set(),
        };
        this._measureVoice(voice);
        return voice;
    }

    /** Point a voice's schedule at a fresh pass 0 of A. */
    _startVoiceAt(voice, when) {
        voice.t0 = when;
        voice.passA = 0;
        voice.passB = 0;
    }

    /**
     * Read a voice's loudness and work out its make-up gain. Measures the
     * cropped region rather than the file, because that is what will be heard.
     *
     * The gain is capped twice over: by LOUDNESS_GAIN_LIMIT_DB either way, and
     * so the region's loudest sample never passes PEAK_CEILING_DB. The second
     * is the bake's own ceiling, so a file the artist is levelling sounds the
     * way it will once saved. `loudnessLimit` names whichever cap bit, so the
     * panel can say why a layer fell short of its target.
     */
    _measureVoice(voice) {
        voice.loudnessPeakDb = null;
        voice.loudnessLimit = null;
        if (voice.config.loudnessTarget == null) {
            voice.loudness = null;
            voice.loudnessGainDb = 0;
            voice.loudnessGain = 1;
            return voice;
        }
        const key = `${voice.config.urlA}@${voice.region.offset.toFixed(3)}`
            + `+${voice.region.duration.toFixed(3)}`;
        if (!this._loudnessCache.has(key)) {
            const peak = regionPeak(voice.bufferA, voice.region);
            this._loudnessCache.set(key, {
                loudness: measureLoudness(voice.bufferA, voice.region),
                peakDb: peak > 0 ? 20 * Math.log10(peak) : null,
            });
        }
        const { loudness: measured, peakDb } = this._loudnessCache.get(key);
        const target = voice.config.loudnessTarget;
        let gainDb = loudnessGainDb(measured, target);
        if (Number.isFinite(measured) && Math.abs(target - measured) > LOUDNESS_GAIN_LIMIT_DB) {
            voice.loudnessLimit = "gain";
        }
        if (peakDb != null && gainDb > PEAK_CEILING_DB - peakDb) {
            gainDb = PEAK_CEILING_DB - peakDb;
            voice.loudnessLimit = "peak";
        }
        voice.loudness = Number.isFinite(measured) ? measured : null;
        voice.loudnessPeakDb = peakDb;
        voice.loudnessGainDb = gainDb;
        voice.loudnessGain = 10 ** (gainDb / 20);
        return voice;
    }

    /**
     * Switch loudness matching on (a target in LUFS) or off (null).
     *
     * Unlike a crop this needs no rebuild: the make-up gain is a factor on the
     * voice's own gain node, so it rides the same ramp the fader does and the
     * schedule never moves.
     */
    setLayerLoudness(index, target) {
        const voice = this.voices[index];
        if (!voice) return null;
        voice.config.loudnessTarget = target == null ? null : Number(target);
        this._measureVoice(voice);
        this._applyMixState();
        return this.layerAnalysis(index);
    }

    /**
     * What the engine learned about a layer once its file was decoded: how long
     * it is, where its crop actually landed after correction, and its loudness.
     * The settings pane cannot size a crop slider or name a reading without
     * these, and none of them are knowable before the fetch.
     */
    layerAnalysis(index) {
        const voice = this.voices[index];
        if (!voice) return null;
        // A blank layer holds a second of silence so its slot keeps a voice.
        // Reporting that as a length would offer the artist a crop over
        // nothing, so it reports no file at all — which is what it has.
        const silent = !voice.config.urlA;
        return {
            duration: silent ? 0 : voice.bufferA.duration,
            trimStart: silent ? 0 : voice.region.offset,
            trimEnd: silent ? 0 : voice.region.offset + voice.region.duration,
            loopCrossfade: silent ? 0 : voice.loopCrossfade,
            loopCrossfadeMax: silent ? 0 : voice.loopCrossfadeMax,
            // How often a pass comes round, in seconds heard — what the
            // panel multiplies out into a cycle length.
            period: silent ? 0 : voice.period,
            loudnessTarget: voice.config.loudnessTarget,
            loudness: voice.loudness,
            loudnessGainDb: voice.loudnessGainDb,
            loudnessPeakDb: voice.loudnessPeakDb,
            loudnessLimit: voice.loudnessLimit,
        };
    }

    /**
     * Where a layer is sounding right now, in seconds into its file — the axis
     * the crop handles are on, so a caller can draw these against the same
     * waveform without converting anything.
     *
     * There is no single playhead to return. A voice runs two schedules of the
     * same crop, and spacing them apart is exactly what `stretch` does, so at
     * any moment a layer has two heads, one, or none: between passes the drift
     * is a gap, not a loop, and nothing is sounding at all. This reports only
     * the passes actually in their region, which is why the array is the return
     * type rather than a number — a single head would have to lie for whichever
     * part of the cycle it was not describing.
     *
     * A schedule can also be sounding more than once over: a loop crossfade
     * pulls each pass into the one before it, and so does a stretch under 1,
     * so each copy offers its recent passes as well as its current one — one
     * head running out the tail while the next comes in at the head.
     *
     * Positions come off the schedule rather than from a timer, so they stay
     * true across a pause: suspending the context stops `currentTime`, and the
     * heads stop with it. They are also worked out rather than read back from
     * what the scheduler has queued, so they are right even where it has not
     * reached yet — and across a rest or a slip, which a running total of
     * periods could not account for.
     */
    layerPlayheads(index) {
        const voice = this.voices[index];
        if (!voice || !this.started || !voice.config.urlA) return [];
        const now = this.context.currentTime;
        const latest = this._latestPassA(voice, now);
        if (latest < 0) return [];
        const heads = [];
        const report = (at, region, rate) => {
            if (at == null || !(region.duration > 0)) return;
            const into = now - at;
            if (into < 0 || into >= region.duration / rate) return;
            heads.push(region.offset + into * rate);
        };
        // Oldest first, and A before B, so the head leaving a tail is reported
        // before the one arriving at a head.
        const oldest = Math.max(0, latest - PLAYHEAD_LOOKBACK);
        const rateA = this._rate(voice, "A");
        const rateB = this._rate(voice, "B");
        for (let k = oldest; k <= latest; k += 1) report(this._startA(voice, k), voice.region, rateA);
        if (voice.config.secondCopy) {
            for (let k = oldest; k <= latest; k += 1) {
                report(this._startB(voice, k), voice.regionB, rateB);
            }
        }
        return heads;
    }

    /** Where pass `k` of copy A begins, in context seconds. */
    _startA(voice, k) {
        return voice.t0 + this._offsetA(voice, k);
    }

    /** How long after pass 0 of A pass `k` begins: the schedule's shape. */
    _offsetA(voice, k) {
        const cycles = Math.floor(k / voice.config.repetitions);
        return k * voice.period + cycles * voice.config.cycleRest;
    }

    /** The tape speed one copy plays at: B may have its own. */
    _rate(voice, copy) {
        if (copy === "B" && voice.config.playbackRateB != null) return voice.config.playbackRateB;
        return voice.config.playbackRate;
    }

    /**
     * How far B has slipped by pass `k`, in seconds. Never while the copies
     * take turns: a slip would walk B into A's turn.
     */
    _slip(voice, k) {
        const step = voice.config.phaseStep;
        if (!(step > 0) || voice.config.takeTurns) return 0;
        return shiftsBefore(k, voice.config.phaseHold, voice.config.phaseHoldAlt)
            * step * voice.period;
    }

    /** How many whole periods B's offset has slipped past since pass 0. */
    _wraps(voice, k) {
        const periods = (offset) => Math.floor(offset / voice.period + 1e-9);
        return periods(voice.offsetB + this._slip(voice, k)) - periods(voice.offsetB);
    }

    /**
     * Where pass `k` of copy B begins, or null when there is no such pass.
     *
     * B is A's partner: it plays the same pass `offsetB` behind, plus however
     * far phase shifting has slipped it. The slip wraps inside the period, so B
     * always sounds within the period of the A pass it belongs to and a cycle's
     * rest silences both copies together. The one pass at which the slip comes
     * all the way round is dropped — played, it would start before the one
     * ahead of it had finished — and B carries on a period later, which is the
     * same place an unwrapped slip would have put it.
     */
    _startB(voice, k) {
        if (!voice.config.secondCopy) return null;
        const wraps = this._wraps(voice, k);
        if (k > 0 && wraps > this._wraps(voice, k - 1)) return null;
        return this._startA(voice, k) + voice.offsetB + this._slip(voice, k)
            - wraps * voice.period;
    }

    /** The last pass of A to have begun by `now`, or -1 before the first. */
    _latestPassA(voice, now) {
        const since = now - voice.t0;
        if (since < 0) return -1;
        const n = voice.config.repetitions;
        const cycle = n * voice.period + voice.config.cycleRest;
        const cycles = Math.floor(since / cycle);
        const into = since - cycles * cycle;
        return cycles * n + Math.min(n - 1, Math.floor(into / voice.period));
    }

    /**
     * Which edges of a seamless sound's pass need a de-click fade: those not
     * butted against the pass before or after it in the same copy. A baked loop
     * joins itself perfectly back to back, so a butted edge is left alone; any
     * other edge — a gap from spacing, a rest, a start delay, a slip — would
     * cut the loop off mid-signal and click.
     *
     * Null for everything else. An unbaked file plays exactly as it always
     * has, and a crossfading pass already has an envelope of its own.
     */
    _edges(voice, copy, k) {
        if (!voice.config.seamless || voice.loopCrossfade > 0) return null;
        const startOf = (i) => {
            if (i < 0) return null;
            return copy === "A" ? this._startA(voice, i) : this._startB(voice, i);
        };
        const region = copy === "A" ? voice.region : voice.regionB;
        const length = region.duration / this._rate(voice, copy);
        const when = startOf(k);
        // B drops a pass where its slip wraps, so its neighbours may be two
        // away rather than one.
        const before = startOf(k - 1) ?? startOf(k - 2);
        const after = startOf(k + 1) ?? startOf(k + 2);
        const butts = (from, to) => from != null && to != null
            && Math.abs(from + length - to) < 1e-6;
        return { fadeIn: !butts(before, when), fadeOut: !butts(when, after) };
    }

    /**
     * The drawable envelope of a file, for the trim panel of a new sound.
     *
     * Addressed by url rather than by layer index on purpose: it goes through
     * `_decode`, so a file the mix already holds is summarised straight off the
     * cached buffer, and one it does not — a track being auditioned before it
     * joins the mix — is fetched once and then shared with the voice that
     * follows. Both answers are memoised, so a redraw never repeats the walk.
     */
    async peaksFor(url, buckets = DEFAULT_PEAK_BUCKETS) {
        const count = Math.max(1, Math.floor(buckets));
        const key = `${url}@${count}`;
        if (!this._peaksCache.has(key)) {
            this._peaksCache.set(
                key,
                this._decode(url).then((buffer) => peaksFromBuffer(buffer, count)),
            );
        }
        try {
            return await this._peaksCache.get(key);
        } catch (error) {
            this._peaksCache.delete(key);
            throw error;
        }
    }

    async setLayers(layers, {
        crossfadeSeconds = this.started ? this.crossfadeSeconds : 0,
        onProgress,
    } = {}) {
        if (this.destroyed) throw new Error("Cannot load a destroyed mixer.");
        const configs = Array.from(layers ?? []);
        const totalFiles = configs.reduce((total, layer) => {
            const normalized = normalizeLayer(layer, total);
            return total + (normalized.urlA === normalized.urlB ? 1 : 2);
        }, 0);
        let loadedFiles = 0;
        const report = () => {
            loadedFiles += 1;
            const detail = { loaded: loadedFiles, total: totalFiles };
            onProgress?.(detail);
            this.dispatchEvent(new CustomEvent("progress", { detail }));
        };

        const prepared = await Promise.all(
            configs.map((layer, index) => this._prepareVoice(layer, index, report)),
        );
        this._throwIfDestroyed();
        const previous = this.voices;
        const now = this.context.currentTime;
        const startAt = Math.max(now + 0.08, Math.ceil(now));

        this.voices = prepared;
        for (const voice of prepared) {
            this._startVoiceAt(voice, startAt + voice.config.startDelay);
        }
        if (crossfadeSeconds > 0) {
            this._fadeInVoices(prepared, startAt, crossfadeSeconds);
        } else {
            this._applyMixState(0);
        }

        if (this.started) this._tick();
        this._retireVoices(previous, crossfadeSeconds);
        this.dispatchEvent(new CustomEvent("layerschange", {
            detail: { count: prepared.length },
        }));
        return prepared;
    }

    /**
     * Rebuild one voice from a new config, crossfading from the old one.
     *
     * The replacement starts straight away: a settings change should be heard
     * as it is made. `delayStart` sends it through its start delay instead,
     * which is what changing the delay itself asks for — without it there
     * would be no way to hear what the delay does.
     */
    async replaceLayer(index, layer, {
        crossfadeSeconds = this.crossfadeSeconds,
        delayStart = false,
    } = {}) {
        this._throwIfDestroyed();
        if (!this.voices[index]) throw new RangeError(`No layer exists at index ${index}.`);
        const replacement = await this._prepareVoice(layer, index);
        this._throwIfDestroyed();
        const previous = this.voices[index];
        const now = this.context.currentTime;
        this._startVoiceAt(
            replacement,
            now + 0.08 + (delayStart ? replacement.config.startDelay : 0),
        );
        this.voices[index] = replacement;
        this._applyMixState(crossfadeSeconds);
        if (this.started) this._tick();
        this._retireVoices([previous], crossfadeSeconds);
        this.dispatchEvent(new CustomEvent("layerreplace", {
            detail: { index, id: replacement.config.id },
        }));
        return replacement;
    }

    /**
     * Rebuild one voice from a new config without restarting it — how a
     * settings change is heard.
     *
     * replaceLayer starts the replacement from its first pass and crossfades
     * over seconds, which is right for a different sound and wrong for the same
     * one retuned: the artist would hear every edit as the layer fading out and
     * starting again. Here the replacement picks up where the old voice has got
     * to — the same pass, the same place in the file — and the two hand over in
     * HANDOFF_SECONDS, so a new rate is a new pitch on the note already
     * sounding and a new crossfade is heard at the next seam.
     *
     * `seek`, in seconds into the file, puts the current pass at that place
     * instead (seekLayer). It is clamped into the kept region.
     *
     * The start delay is only a wait before the first pass, so changing it
     * while the layer is already playing changes nothing that can be heard;
     * during the wait, the wait is re-measured against the new delay.
     */
    async retimeLayer(index, layer, { seek = null } = {}) {
        this._throwIfDestroyed();
        if (!this.voices[index]) throw new RangeError(`No layer exists at index ${index}.`);
        const replacement = await this._prepareVoice(layer, index);
        this._throwIfDestroyed();
        const previous = this.voices[index];
        if (!previous) throw new RangeError(`No layer exists at index ${index}.`);
        const at = this.context.currentTime + HANDOFF_LEAD;
        this._continue(replacement, previous, at, seek);
        this.voices[index] = replacement;
        // Straight to its level: the passes it joins part-way fade themselves
        // in (_schedule), and the ones still to come begin as they always do.
        const param = replacement.gain.gain;
        param.cancelScheduledValues(0);
        param.setValueAtTime(this._targetGain(replacement), this.context.currentTime);
        if (this.started) this._tick();
        this._retireVoices([previous], HANDOFF_SECONDS, at);
        this.dispatchEvent(new CustomEvent("layerreplace", {
            detail: { index, id: replacement.config.id },
        }));
        return replacement;
    }

    /**
     * Play a layer from `position` seconds into its file, now. The rest of the
     * mix carries on untouched. The pass count is kept, so the second copy's
     * phase slip and the cycle stay where they were.
     */
    seekLayer(index, position) {
        const voice = this.voices[index];
        if (!voice) throw new RangeError(`No layer exists at index ${index}.`);
        return this.retimeLayer(index, { ...voice.config }, { seek: Number(position) || 0 });
    }

    /**
     * Point `voice` at the moment `previous` is at, as of `at` — or at `seek`.
     *
     * The anchor is A's pass: the one `previous` is in, and how far into it.
     * That is carried over as a position in the file, so it survives a change
     * of rate or crop, and t0 is worked back from it. Everything else — which
     * earlier passes are still sounding, where B is, the next seam — then
     * falls out of the ordinary schedule arithmetic, and the scheduler joins
     * whatever is under way part-way through (`handoff`).
     */
    _continue(voice, previous, at, seek) {
        const origin = previous.t0 - previous.config.startDelay;
        const latest = this._latestPassA(previous, at);
        if (!this.started || (latest < 0 && seek == null)) {
            // Not playing yet, or still waiting out its start delay: the wait
            // is measured from when the layer began, against the new delay.
            this._startVoiceAt(voice, origin + voice.config.startDelay);
            return;
        }
        const k = Math.max(0, latest);
        const rate = voice.config.playbackRate;
        const { offset, duration } = voice.region;
        const length = duration / rate;
        // The time from this pass's start to the next one's.
        const step = this._offsetA(voice, k + 1) - this._offsetA(voice, k);
        let into;
        if (seek != null) {
            into = (Math.min(Math.max(seek, offset), offset + duration) - offset) / rate;
        } else {
            const oldRate = previous.config.playbackRate;
            const heard = at - this._startA(previous, k);
            const oldLength = previous.region.duration / oldRate;
            const position = previous.region.offset + heard * oldRate;
            if (heard >= oldLength) {
                // Between passes: the same silence already sat through, but
                // never past where the new schedule's next pass begins.
                into = length + Math.min(heard - oldLength, Math.max(0, step - length));
            } else if (position >= offset + duration) {
                // A crop that now ends before the playhead: this pass is over,
                // and the next begins now, or after whatever gap is left.
                into = Math.min(step, length);
            } else {
                into = Math.max(0, position - offset) / rate;
            }
        }
        voice.t0 = at - into - this._offsetA(voice, k);
        // A few passes back, not just this one: a crossfade or a close spacing
        // leaves earlier passes still sounding, and B trails its own A pass.
        voice.passA = Math.max(0, k - PLAYHEAD_LOOKBACK);
        voice.passB = voice.passA;
        voice.handoff = at;
    }

    /**
     * Append one layer without disturbing the voices already playing.
     *
     * setLayers() could do this, but it rebuilds every voice and restarts each
     * schedule from a common `startAt`, so every existing layer audibly jumps
     * back into phase. The `+` button adds layers one at a time on top of a
     * running mix, so it needs the surgical version: prepare the new voice,
     * fade it in, leave the rest alone.
     */
    async addLayer(layer, { crossfadeSeconds = this.crossfadeSeconds } = {}) {
        if (this.destroyed) throw new Error("Cannot add a layer to a destroyed mixer.");
        const voice = await this._prepareVoice(layer, this.voices.length);
        this._throwIfDestroyed();
        const now = this.context.currentTime;
        this._startVoiceAt(voice, now + 0.08 + voice.config.startDelay);
        this.voices.push(voice);
        this._applyMixState(crossfadeSeconds);
        if (this.started) this._tick();
        this.dispatchEvent(new CustomEvent("layerschange", {
            detail: { count: this.voices.length },
        }));
        return voice;
    }

    /**
     * Drop the layer at `index`, fading it out before its sources are stopped.
     * Remaining voices keep their schedules, so removing a layer never
     * re-phases the mix.
     */
    removeLayer(index, { crossfadeSeconds = this.crossfadeSeconds } = {}) {
        const voice = this.voices[index];
        if (!voice) throw new RangeError(`No layer exists at index ${index}.`);
        this.voices.splice(index, 1);
        this._applyMixState(crossfadeSeconds);
        this._retireVoices([voice], crossfadeSeconds);
        this.dispatchEvent(new CustomEvent("layerschange", {
            detail: { count: this.voices.length },
        }));
        return voice;
    }

    /**
     * Fade voices out and stop them. `from` holds them at their level until
     * then, so a handoff can line the fade up with its replacement's fade in.
     */
    _retireVoices(voices, fadeSeconds, from = this.context.currentTime) {
        const now = this.context.currentTime;
        const begins = Math.max(now, from);
        for (const voice of voices) {
            if (!voice) continue;
            const param = voice.gain.gain;
            const level = param.value;
            param.cancelScheduledValues(now);
            param.setValueAtTime(level, now);
            if (begins > now) param.setValueAtTime(level, begins);
            param.linearRampToValueAtTime(0, begins + fadeSeconds);
        }
        const delay = Math.max(0, (begins - now + fadeSeconds) * 1000 + 120);
        globalThis.setTimeout(() => {
            for (const voice of voices) {
                if (!voice) continue;
                stopSources(voice);
                try {
                    voice.gain.disconnect();
                } catch {
                    // Already disconnected.
                }
            }
        }, delay);
    }

    _targetGain(voice) {
        const anySolo = this.voices.some((candidate) => candidate.config.solo);
        const silenced = voice.config.muted || (anySolo && !voice.config.solo);
        // Loudness matching multiplies the fader rather than replacing it, so
        // the artist keeps a fader that still means what it did — the make-up
        // gain only decides where its 50% sits. The product may exceed 1; the
        // master limiter is what catches that, and eight layers summing at unity
        // would have needed it anyway.
        return silenced ? 0 : gainFromSlider(voice.config.level) * voice.loudnessGain;
    }

    /**
     * Bring newly scheduled voices up from silence when their audio begins.
     *
     * Decoding can leave `startAt` well ahead of `currentTime`. Starting the
     * ramp immediately would spend part (or all) of the fade before a source
     * is audible, which makes first playback and loaded mixes sound abrupt.
     */
    _fadeInVoices(voices, startAt, rampSeconds = this.crossfadeSeconds) {
        const now = this.context.currentTime;
        const begins = Math.max(now, startAt);
        const duration = Math.max(0, rampSeconds);
        for (const voice of voices) {
            const param = voice.gain.gain;
            const target = this._targetGain(voice);
            param.cancelScheduledValues(now);
            param.setValueAtTime(param.value, now);
            param.setValueAtTime(0, begins);
            if (duration > 0) {
                param.linearRampToValueAtTime(target, begins + duration);
            } else {
                param.setValueAtTime(target, begins);
            }
        }
    }

    _applyMixState(rampSeconds = 0.1) {
        const now = this.context.currentTime;
        for (const voice of this.voices) {
            const target = this._targetGain(voice);
            const param = voice.gain.gain;
            param.cancelScheduledValues(now);
            param.setValueAtTime(param.value, now);
            if (rampSeconds > 0) {
                param.linearRampToValueAtTime(target, now + rampSeconds);
            } else {
                param.setValueAtTime(target, now);
            }
        }
    }

    setLayerGain(index, value) {
        const voice = this.voices[index];
        if (!voice) return;
        voice.config.level = clamp(value);
        voice.config.muted = false;
        this._applyMixState();
    }

    setLayerMute(index, muted) {
        const voice = this.voices[index];
        if (!voice) return;
        voice.config.muted = Boolean(muted);
        this._applyMixState();
    }

    setLayerSolo(index, solo) {
        const voice = this.voices[index];
        if (!voice) return;
        voice.config.solo = Boolean(solo);
        this._applyMixState();
    }

    /**
     * The loop crossfade for one pass: a gain node that rises over the pass's
     * first `loopCrossfade` seconds and falls over its last.
     *
     * Per pass rather than per voice, because that is what a crossfade is —
     * two passes overlap, and each has to be somewhere different in its own
     * fade at the same moment. The voice's own gain node cannot do that: it
     * carries the fader, the mute and the loudness make-up gain, which belong
     * to the whole layer.
     *
     * Timed in context seconds, so a layer played at half speed fades for the
     * seconds the artist asked for rather than for half of them.
     *
     * Null when there is no fade to make — a pass too short to hold one, which
     * is the only case left once the caller has checked the layer asked for one
     * at all. A zero-length value curve is a RangeError, not a no-op.
     *
     * `from` is when the pass is actually joined, if a handoff joined it
     * part-way: whatever of either ramp is already behind it is left out, and
     * a ramp it lands inside carries on from that point of the curve.
     */
    _envelope(voice, when, region, from = when, rate = voice.config.playbackRate) {
        const pass = (region?.duration || 0) / Math.max(0.01, rate);
        // Half a pass is the ceiling, less a millisecond: at the ceiling the
        // head ramp would end on the exact moment the tail ramp begins, and an
        // automation event landing on the end of a value curve is the one case
        // implementations disagree about. A millisecond of hold between them
        // settles it and is far under anything audible.
        const fade = Math.min(voice.loopCrossfade, Math.max(0, pass - 0.001) / 2);
        if (!(fade > 0)) return null;
        const node = this.context.createGain();
        node.connect(voice.gain);
        const param = node.gain;
        const headEnd = when + fade;
        const tail = when + pass - fade;
        const end = when + pass;
        // Anything under a tenth of a millisecond left of a ramp is past it.
        const inside = (edge) => edge - from > 1e-4;
        if (from <= when) {
            param.setValueCurveAtTime(FADE_IN, when, fade);
        } else if (inside(headEnd)) {
            param.setValueCurveAtTime(
                remainingCurve(true, (from - when) / fade), from, headEnd - from);
        }
        if (from <= tail) {
            param.setValueCurveAtTime(FADE_OUT, tail, fade);
        } else if (inside(end)) {
            param.setValueCurveAtTime(
                remainingCurve(false, (from - tail) / fade), from, end - from);
        }
        return node;
    }

    /**
     * The de-click fades for one pass of a seamless sound: a gain node that
     * ramps up over the pass's first DECLICK_SECONDS, down over its last, or
     * both — only on the edges `_edges` found unbutted. Null when neither edge
     * needs one, so a loop played back to back goes straight to the voice.
     *
     * A pass joined part-way (`from`) has no head edge left to fade — the
     * handoff's own fade in covers where it was joined.
     */
    _declick(voice, when, region, edges, from = when, rate = voice.config.playbackRate) {
        const late = from > when;
        const fadeIn = Boolean(edges?.fadeIn) && !late;
        if (!fadeIn && !edges?.fadeOut) return null;
        const pass = (region?.duration || 0) / Math.max(0.01, rate);
        const fade = Math.min(DECLICK_SECONDS, Math.max(0, pass - 0.001) / 2);
        if (!(fade > 0)) return null;
        const node = this.context.createGain();
        node.connect(voice.gain);
        const param = node.gain;
        param.setValueAtTime(fadeIn ? 0 : 1, from);
        if (fadeIn) param.linearRampToValueAtTime(1, when + fade);
        if (edges.fadeOut) {
            if (when + pass - fade > from) param.setValueAtTime(1, when + pass - fade);
            param.linearRampToValueAtTime(0, when + pass);
        }
        return node;
    }

    _schedule(voice, buffer, when, region, edges = null, rate = voice.config.playbackRate) {
        // A pass that began before this voice took over (retimeLayer) is
        // joined where it has got to, not played from its head — and not at
        // all if it is already over.
        const from = Math.max(when, voice.handoff);
        const late = from > when;
        const skip = (from - when) * rate;
        if (late && !(region?.duration > skip + 1e-6)) return;
        const source = this.context.createBufferSource();
        source.buffer = buffer;
        source.loop = false;
        source.playbackRate.value = rate;
        const envelope = voice.loopCrossfade > 0
            ? this._envelope(voice, when, region, from, rate)
            : this._declick(voice, when, region, edges, from, rate);
        // Starting mid-signal would click, so a joined pass fades in over the
        // handoff while the voice it takes over from fades out.
        let entry = null;
        if (late) {
            entry = this.context.createGain();
            entry.connect(envelope ?? voice.gain);
            entry.gain.setValueAtTime(0, from);
            entry.gain.linearRampToValueAtTime(1, from + HANDOFF_SECONDS);
        }
        source.connect(entry ?? envelope ?? voice.gain);
        voice.activeSources.add(source);
        source.onended = () => {
            voice.activeSources.delete(source);
            for (const node of [source, entry, envelope]) {
                try {
                    node?.disconnect();
                } catch {
                    // Already disconnected.
                }
            }
        };
        // The crop is applied per source rather than by rewriting the buffer:
        // both offset and duration are buffer-time, so a cropped voice shares
        // its cached buffer with every other layer pointing at the same file.
        if (region && region.duration > 0) {
            source.start(from, region.offset + skip, region.duration - skip);
        } else {
            source.start(when);
        }
    }

    /**
     * Queue every pass that begins before the look-ahead horizon.
     *
     * A counts its passes and B follows them; where each one begins is
     * `_startA` / `_startB`'s business, so a rest, a start delay and a phase
     * slip all come out of the same arithmetic the playheads read.
     */
    _tick = () => {
        if (!this.started || this.destroyed) return;
        const horizon = this.context.currentTime + this.lookAhead;
        for (const voice of this.voices) {
            for (
                let when = this._startA(voice, voice.passA);
                when < horizon;
                when = this._startA(voice, voice.passA)
            ) {
                this._schedule(voice, voice.bufferA, when, voice.region,
                    this._edges(voice, "A", voice.passA));
                voice.passA += 1;
            }
            if (!voice.config.secondCopy) continue;
            // B never begins before its A pass, so once A's pass is past the
            // horizon there is nothing more of B to queue either — which is
            // also what stops a dropped pass being stepped over forever.
            while (this._startA(voice, voice.passB) < horizon) {
                const when = this._startB(voice, voice.passB);
                if (when != null) {
                    if (when >= horizon) break;
                    this._schedule(voice, voice.bufferB, when, voice.regionB,
                        this._edges(voice, "B", voice.passB), this._rate(voice, "B"));
                }
                voice.passB += 1;
            }
        }
    };

    async play() {
        if (this.destroyed) return;
        await this.context.resume();
        if (!this.started) {
            const startAt = Math.max(this.context.currentTime + 0.08, Math.ceil(this.context.currentTime));
            for (const voice of this.voices) {
                this._startVoiceAt(voice, startAt + voice.config.startDelay);
            }
            this._fadeInVoices(this.voices, startAt);
            this.started = true;
            this._tick();
            this._timer = globalThis.setInterval(this._tick, this.schedulerInterval);
        }
        this.dispatchEvent(new CustomEvent("statechange", { detail: { state: "playing" } }));
    }

    async pause() {
        if (this.destroyed) return;
        await this.context.suspend();
        this.dispatchEvent(new CustomEvent("statechange", { detail: { state: "paused" } }));
    }

    async resume() {
        if (this.destroyed) return;
        await this.context.resume();
        this.dispatchEvent(new CustomEvent("statechange", { detail: { state: "playing" } }));
    }

    destroy() {
        if (this.destroyed) return;
        this.destroyed = true;
        this.started = false;
        if (this._timer) globalThis.clearInterval(this._timer);
        for (const voice of this.voices) {
            stopSources(voice);
            try {
                voice.gain.disconnect();
            } catch {
                // Already disconnected.
            }
        }
        this.voices = [];
        this._bufferCache.clear();
        this._loudnessCache.clear();
        this._peaksCache.clear();
        this.context.close().catch(() => {});
        this.dispatchEvent(new CustomEvent("statechange", { detail: { state: "destroyed" } }));
    }
}
