import test from "node:test";
import assert from "node:assert/strict";

import {
    MixerDestroyedError,
    PEAK_CEILING_DB,
    SoundscapeMixer,
    cropRegion,
    gainFromSlider,
    loudnessGainDb,
    measureLoudness,
    roundToEighth,
    shiftsBefore,
    timingForBuffers,
} from "./soundscape-mixer.js";

// Enough of the Web Audio surface for the graph the mixer builds in its
// constructor. Nothing here makes sound — the tests only care about which
// voices exist and what their target gains are.
function fakeParam(value = 0) {
    return {
        value,
        maxValue: 1,
        events: [],
        // Every value curve scheduled on this param, which is where a loop
        // crossfade shows up: one ramp up and one down per scheduled pass.
        curves: [],
        setTargetAtTime() {},
        cancelScheduledValues() {},
        setValueAtTime(next) {
            this.value = next;
            this.events.push({ type: "set", value: next, when: arguments[1] });
        },
        linearRampToValueAtTime(next) {
            this.value = next;
            this.events.push({ type: "ramp", value: next, when: arguments[1] });
        },
        setValueCurveAtTime(curve, when, duration) {
            this.curves.push({ curve, when, duration });
        },
    };
}

function fakeNode() {
    const node = {
        gain: fakeParam(),
        threshold: fakeParam(),
        knee: fakeParam(),
        ratio: fakeParam(),
        attack: fakeParam(),
        release: fakeParam(),
        connections: [],
        connect(destination) {
            node.connections.push(destination);
            return destination;
        },
        disconnect() {},
    };
    return node;
}

// `starts` collects the arguments every scheduled source was started with,
// which is where a crop shows up: the engine never rewrites a buffer, it hands
// the kept region to start(when, offset, duration).
//
// `context.gains` collects every gain node built on it, in order. A crossfading
// pass gets one of its own — the voice's gain node carries the fader and cannot
// also hold a fade two passes are at different points of.
function fakeContext(starts = []) {
    const context = {
        currentTime: 0,
        sampleRate: 44100,
        gains: [],
        createBuffer: (channels, length, rate) => ({ duration: length / rate }),
        destination: fakeNode(),
        createGain: () => {
            const node = fakeNode();
            context.gains.push(node);
            return node;
        },
        createChannelSplitter: fakeNode,
        createChannelMerger: fakeNode,
        createDynamicsCompressor: fakeNode,
        createBufferSource: () => ({
            ...fakeNode(),
            playbackRate: fakeParam(1),
            buffer: null,
            start(...args) {
                starts.push(args);
            },
            stop() {},
        }),
        resume: async () => {},
        suspend: async () => {},
        close: async () => {},
    };
    return context;
}

// A mixer whose decoding is stubbed out, so layers resolve without fetch.
function stubbedMixer(starts) {
    const mixer = new SoundscapeMixer({ audioContext: fakeContext(starts) });
    mixer._decode = async () => ({ duration: 24 });
    return mixer;
}

/**
 * A buffer holding a steady tone, which is the only signal whose loudness can
 * be predicted on paper: a full-scale-referenced sine at -N dBFS in both
 * channels measures -N LUFS, so `amplitudeForLufs` doubles as the expected
 * reading.
 */
function toneBuffer({
    lufs = -23,
    frequency = 1000,
    seconds = 3,
    sampleRate = 48000,
    channels = 2,
} = {}) {
    const length = Math.round(seconds * sampleRate);
    const amplitude = 10 ** (lufs / 20);
    const data = new Float32Array(length);
    for (let i = 0; i < length; i += 1) {
        data[i] = amplitude * Math.sin(2 * Math.PI * frequency * i / sampleRate);
    }
    return {
        sampleRate,
        numberOfChannels: channels,
        length,
        duration: length / sampleRate,
        getChannelData: () => data,
    };
}

test("rounds decoded durations to eighths of a second", () => {
    assert.equal(roundToEighth(23.619), 23.625);
    assert.equal(roundToEighth(24), 24);
});

test("computes the myNoise-style A/B period and offset", () => {
    const timing = timingForBuffers(23.619, 60, {
        stretch: 1.75,
        playbackRate: 1,
    });
    assert.equal(timing.offsetB, 20.671875);
    assert.equal(timing.period, 73.171875);
});

test("playback rate changes both pitch speed and schedule duration", () => {
    const normal = timingForBuffers(24, 24);
    const octaveUp = timingForBuffers(24, 24, { playbackRate: 2 });
    assert.equal(octaveUp.period, normal.period / 2);
    assert.equal(octaveUp.offsetB, normal.offsetB / 2);
});

test("uses a cubic perceptual fader curve", () => {
    assert.equal(gainFromSlider(0), 0);
    assert.equal(gainFromSlider(0.5), 0.125);
    assert.equal(gainFromSlider(1), 1);
});

test("first playback fades in when its scheduled audio begins", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav", level: 1 }]);

    await mixer.play();

    const events = mixer.voices[0].gain.gain.events;
    mixer.destroy();
    assert.deepEqual(events.slice(-2), [
        { type: "set", value: 0, when: 0.08 },
        { type: "ramp", value: 1, when: 0.08 + mixer.crossfadeSeconds },
    ]);
});

test("a loaded mix fades replacement voices from their scheduled start", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "old", url: "old.wav" }]);
    await mixer.play();
    mixer.context.currentTime = 0.25;

    await mixer.setLayers([{ id: "new", url: "new.wav", level: 0.5 }]);

    const events = mixer.voices[0].gain.gain.events;
    mixer.destroy();
    assert.deepEqual(events.slice(-2), [
        { type: "set", value: 0, when: 1 },
        { type: "ramp", value: 0.125, when: 1 + mixer.crossfadeSeconds },
    ]);
});

test("addLayer appends a voice and leaves the existing ones in place", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav", level: 0.5 }]);
    const first = mixer.voices[0];

    await mixer.addLayer({ id: "b", url: "b.wav", level: 0.5 });

    assert.equal(mixer.voices.length, 2);
    assert.equal(mixer.voices[0], first, "the original voice is not rebuilt");
    assert.equal(mixer.voices[1].config.id, "b");
    mixer.destroy();
});

test("addLayer reports the new count on layerschange", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav" }]);
    let count = null;
    mixer.addEventListener("layerschange", (event) => {
        count = event.detail.count;
    });

    await mixer.addLayer({ id: "b", url: "b.wav" });

    assert.equal(count, 2);
    mixer.destroy();
});

// A mixer whose decodes wait until the test lets them finish, which is how a
// mixer gets torn down mid-load: HTMX swaps the card out, or the store starts a
// fresh load, while the files are still arriving.
function pendingMixer() {
    const context = fakeContext();
    const mixer = new SoundscapeMixer({ audioContext: context });
    const releases = [];
    mixer._decode = () => new Promise((resolve) => {
        releases.push(() => resolve({ duration: 24 }));
    });
    const releaseAll = () => releases.splice(0).forEach((release) => release());
    return { context, mixer, releaseAll };
}

test("a mixer destroyed while its files decode builds nothing on the closed context", async () => {
    const { context, mixer, releaseAll } = pendingMixer();
    const loading = mixer.setLayers([
        { id: "a", url: "a.wav" },
        { id: "b", url: "b.wav" },
        { id: "c", url: "c.wav" },
    ]);
    const gainsBuilt = context.gains.length;

    mixer.destroy();
    releaseAll();

    await assert.rejects(loading, MixerDestroyedError);
    assert.equal(context.gains.length, gainsBuilt);
    assert.deepEqual(mixer.voices, []);
});

test("a layer added to a mixer destroyed mid-decode is never built", async () => {
    const { context, mixer, releaseAll } = pendingMixer();
    const adding = mixer.addLayer({ id: "a", url: "a.wav" });
    const gainsBuilt = context.gains.length;

    mixer.destroy();
    releaseAll();

    await assert.rejects(adding, MixerDestroyedError);
    assert.equal(context.gains.length, gainsBuilt);
});

test("removeLayer drops only the targeted voice", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([
        { id: "a", url: "a.wav" },
        { id: "b", url: "b.wav" },
        { id: "c", url: "c.wav" },
    ]);
    const kept = [mixer.voices[0], mixer.voices[2]];

    const removed = mixer.removeLayer(1, { crossfadeSeconds: 0 });

    assert.equal(removed.config.id, "b");
    assert.deepEqual(mixer.voices, kept);
    mixer.destroy();
});

test("removeLayer rejects an index that holds no voice", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav" }]);

    assert.throws(() => mixer.removeLayer(4), RangeError);
    mixer.destroy();
});

test("a layer with no audio still occupies a voice", async () => {
    const mixer = stubbedMixer();
    mixer._decode = async () => {
        throw new Error("a blank layer must not be decoded");
    };

    await mixer.setLayers([{ id: "blank", url: "" }]);

    assert.equal(mixer.voices.length, 1, "the blank layer holds its slot");
    assert.equal(mixer.voices[0].config.id, "blank");
    mixer.destroy();
});

test("a blank layer keeps later layers aligned with their faders", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([
        { id: "a", url: "a.wav" },
        { id: "blank", url: "" },
        { id: "c", url: "c.wav" },
    ]);

    mixer.setLayerGain(2, 0.9);

    assert.equal(mixer.voices[2].config.id, "c");
    assert.equal(mixer.voices[2].config.level, 0.9);
    mixer.destroy();
});

test("a soloed layer still silences the others after a layer is added", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav", level: 1, solo: true }]);

    await mixer.addLayer({ id: "b", url: "b.wav", level: 1 });

    assert.equal(mixer.voices[0].gain.gain.value, 1);
    assert.equal(mixer.voices[1].gain.gain.value, 0, "the un-soloed newcomer stays down");
    mixer.destroy();
});

test("an uncropped layer keeps the whole file", () => {
    assert.deepEqual(cropRegion(24, {}), { offset: 0, duration: 24 });
    assert.deepEqual(cropRegion(24, { trimStart: 0, trimEnd: null }), {
        offset: 0,
        duration: 24,
    });
});

test("crop handles are corrected rather than trusted", () => {
    assert.deepEqual(cropRegion(24, { trimStart: 4, trimEnd: 10 }), {
        offset: 4,
        duration: 6,
    });
    // A start dragged past its end backs off far enough to leave audio behind.
    assert.deepEqual(cropRegion(24, { trimStart: 20, trimEnd: 5 }), {
        offset: 4.75,
        duration: 0.25,
    });
    // A crop left over from a longer file cannot run off the end of this one.
    assert.deepEqual(cropRegion(24, { trimStart: 0, trimEnd: 100 }), {
        offset: 0,
        duration: 24,
    });
    assert.deepEqual(cropRegion(0, { trimStart: 3, trimEnd: 9 }), {
        offset: 0,
        duration: 0,
    });
});

test("the drift period follows the cropped length, not the file", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav" }]);
    const whole = mixer.voices[0].period;

    await mixer.replaceLayer(0, { id: "a", url: "a.wav", trim_start: 0, trim_end: 12 });

    assert.equal(whole, timingForBuffers(24, 24).period);
    assert.equal(mixer.voices[0].period, timingForBuffers(12, 12).period);
    mixer.destroy();
});

test("a cropped layer schedules only the stretch it kept", async () => {
    const starts = [];
    const mixer = stubbedMixer(starts);
    await mixer.setLayers([{ id: "a", url: "a.wav", trim_start: 4, trim_end: 10 }]);

    await mixer.play();
    mixer.destroy();

    assert.ok(starts.length > 0, "the scheduler ran");
    for (const [, offset, duration] of starts) {
        assert.equal(offset, 4, "each pass starts at the crop");
        assert.equal(duration, 6, "and stops at the other end of it");
    }
});

test("layerAnalysis reports what only a decoded file can say", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([
        { id: "a", url: "a.wav", trim_start: 30, trim_end: 40 },
        { id: "blank", url: "" },
    ]);

    assert.deepEqual(mixer.layerAnalysis(0), {
        duration: 24,
        trimStart: 23.75,
        trimEnd: 24,
        loopCrossfade: 0,
        // Half of the quarter-second the crop left, which is all a repeat of it
        // could overlap.
        loopCrossfadeMax: 0.125,
        // The quarter-second pass at the default 1.75 stretch.
        period: 0.4375,
        loudnessTarget: null,
        loudness: null,
        loudnessGainDb: 0,
        loudnessPeakDb: null,
        loudnessLimit: null,
    });
    // A blank layer plays a silent buffer; offering a crop over it would be a
    // crop over nothing, so it reports no file rather than a one-second one.
    assert.deepEqual(mixer.layerAnalysis(1), {
        duration: 0,
        trimStart: 0,
        trimEnd: 0,
        loopCrossfade: 0,
        loopCrossfadeMax: 0,
        period: 0,
        loudnessTarget: null,
        loudness: null,
        loudnessGainDb: 0,
        loudnessPeakDb: null,
        loudnessLimit: null,
    });
    mixer.destroy();
});

// The loop crossfade: each repeat is pulled into the one before it by the fade
// length, and both ends of every pass are ramped so the seam is crossed rather
// than butted. These pin the schedule arithmetic and the envelope it implies.

test("a loop crossfade pulls each repeat into the one before it", () => {
    const plain = timingForBuffers(24, 24);
    const faded = timingForBuffers(24, 24, { loopCrossfade: 3 });

    assert.equal(faded.loopCrossfade, 3);
    assert.equal(faded.period, plain.period - 3);
    assert.equal(faded.offsetB, plain.offsetB, "where B sits is the stretch's business");
});

test("a crossfade is capped at what the pass and the period can take", () => {
    // Half the pass: past that a pass's own head and tail ramps would cross.
    assert.equal(timingForBuffers(24, 24).loopCrossfadeMax, 12);
    assert.equal(timingForBuffers(24, 24, { loopCrossfade: 30 }).loopCrossfade, 12);
    // Half the period. A stretch under 1 already repeats before a pass has
    // ended, so the pass length is no longer the binding limit — without this
    // the scheduler would end up firing at its floor.
    const tight = timingForBuffers(24, 24, { stretch: 0.5, loopCrossfade: 12 });
    assert.equal(tight.loopCrossfadeMax, 6);
    assert.equal(tight.period, 6);
    // A fade is in seconds heard, so twice the rate is half the pass to fit in.
    assert.equal(timingForBuffers(24, 24, { playbackRate: 2 }).loopCrossfadeMax, 6);
    // The shorter of two different files is what has to hold the fade.
    assert.equal(timingForBuffers(24, 8).loopCrossfadeMax, 4);
});

test("the drift period makes room for the crossfade a layer asked for", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav", loop_crossfade: 4 }]);

    assert.equal(mixer.voices[0].loopCrossfade, 4);
    assert.equal(mixer.voices[0].period, timingForBuffers(24, 24).period - 4);
    assert.equal(mixer.layerAnalysis(0).loopCrossfade, 4);
    mixer.destroy();
});

test("each crossfading pass fades in and out over an envelope of its own", async () => {
    const starts = [];
    const mixer = stubbedMixer(starts);
    await mixer.setLayers([{ id: "a", url: "a.wav", loop_crossfade: 3 }]);

    await mixer.play();
    const envelopes = mixer.context.gains.filter((node) => node.gain.curves.length);
    mixer.destroy();

    assert.ok(starts.length > 0, "the scheduler ran");
    assert.equal(envelopes.length, starts.length, "one envelope per scheduled pass");
    for (const envelope of envelopes) {
        const [rise, fall] = envelope.gain.curves;
        assert.equal(rise.duration, 3, "up over the head of the pass");
        assert.equal(fall.duration, 3, "and down over its tail");
        // 24 seconds of file, so the fall begins three seconds before the end.
        assert.equal(Number((fall.when - rise.when).toFixed(3)), 21);
        assert.equal(rise.curve[0], 0);
        assert.ok(fall.curve.at(-1) < 1e-6, "the pass ends silent");
        // Equal power, not linear: halfway through, both sides sit at -3dB.
        assert.ok(Math.abs(rise.curve[63] - 2 ** -0.5) < 0.02);
    }
});

test("a crossfade dragged to its ceiling still leaves the two ramps apart", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav", loop_crossfade: 99 }]);

    await mixer.play();
    const applied = mixer.layerAnalysis(0).loopCrossfade;
    const [{ gain }] = mixer.context.gains.filter((node) => node.gain.curves.length);
    mixer.destroy();

    assert.equal(applied, 12, "half the pass, and no further");
    const [rise, fall] = gain.curves;
    // Where the two ramps would otherwise meet exactly, which is the one case
    // Web Audio implementations disagree about.
    assert.ok(fall.when > rise.when + rise.duration, "the ramps do not touch");
});

test("a layer with no crossfade plays straight onto its own gain node", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav" }]);

    await mixer.play();
    const faded = mixer.context.gains.filter((node) => node.gain.curves.length);
    mixer.destroy();

    assert.deepEqual(faded, [], "no envelope is built for a hard join");
});

test("a steady tone measures the loudness it was built to", () => {
    assert.ok(Math.abs(measureLoudness(toneBuffer({ lufs: -23 })) + 23) < 0.1);
    assert.ok(Math.abs(measureLoudness(toneBuffer({ lufs: -33 })) + 33) < 0.1);
});

test("loudness is read at whatever rate the file decoded at", () => {
    // The standard prints its filter coefficients at 48k only. Our library is
    // mostly 44.1k, so the coefficients are re-derived per rate — if they were
    // not, the same tone would read differently on either side.
    const at48 = measureLoudness(toneBuffer({ lufs: -23, sampleRate: 48000 }));
    const at441 = measureLoudness(toneBuffer({ lufs: -23, sampleRate: 44100 }));
    assert.ok(Math.abs(at48 - at441) < 0.1);
});

test("loudness measures the cropped region, not the file", () => {
    const loud = toneBuffer({ lufs: -20, seconds: 4 });
    const quiet = toneBuffer({ lufs: -40, seconds: 4 });
    // Four loud seconds followed by four quiet ones.
    const spliced = {
        ...loud,
        length: loud.length * 2,
        duration: loud.duration * 2,
        getChannelData: () => {
            const data = new Float32Array(loud.length * 2);
            data.set(loud.getChannelData(0), 0);
            data.set(quiet.getChannelData(0), loud.length);
            return data;
        },
    };

    const head = measureLoudness(spliced, { offset: 0, duration: 4 });
    const tail = measureLoudness(spliced, { offset: 4, duration: 4 });

    assert.ok(Math.abs(head + 20) < 0.2);
    assert.ok(Math.abs(tail + 40) < 0.2);
});

test("nothing to measure is not the same as very quiet", () => {
    assert.equal(measureLoudness(toneBuffer({ lufs: -23, seconds: 0.3 })), -Infinity);
    assert.equal(measureLoudness({ duration: 24 }), -Infinity, "an undecoded stub");
    assert.equal(loudnessGainDb(-Infinity, -23), 0, "so the layer is left alone");
});

test("make-up gain is capped both ways", () => {
    assert.equal(loudnessGainDb(-33, -23), 10);
    assert.equal(loudnessGainDb(-13, -23), -10);
    assert.equal(loudnessGainDb(-60, -23), 24, "a near-silent source is not shouted at");
    assert.equal(loudnessGainDb(-2, -40), -24);
});

test("loudness matching multiplies the fader rather than replacing it", async () => {
    const mixer = new SoundscapeMixer({ audioContext: fakeContext() });
    mixer._decode = async () => toneBuffer({ lufs: -33 });
    await mixer.setLayers([{ id: "a", url: "a.wav", level: 1 }]);
    assert.equal(mixer.voices[0].gain.gain.value, 1, "off until it is asked for");

    const analysis = mixer.setLayerLoudness(0, -23);

    assert.ok(Math.abs(analysis.loudness + 33) < 0.1);
    assert.ok(Math.abs(analysis.loudnessGainDb - 10) < 0.1);
    assert.ok(Math.abs(mixer.voices[0].gain.gain.value - 10 ** 0.5) < 0.01);
    // Halfway down the fader still means halfway down, ten dB up or not.
    mixer.setLayerGain(0, 0.5);
    assert.ok(Math.abs(mixer.voices[0].gain.gain.value - 0.125 * 10 ** 0.5) < 0.01);

    mixer.setLayerLoudness(0, null);
    assert.equal(mixer.voices[0].gain.gain.value, 0.125);
    mixer.destroy();
});

test("a muted layer stays silent however loud it measured", async () => {
    const mixer = new SoundscapeMixer({ audioContext: fakeContext() });
    mixer._decode = async () => toneBuffer({ lufs: -45 });
    await mixer.setLayers([{ id: "a", url: "a.wav", level: 1, muted: true }]);

    mixer.setLayerLoudness(0, -23);

    assert.equal(mixer.voices[0].gain.gain.value, 0);
    mixer.destroy();
});

// A voice runs two schedules of the same crop, spaced by `stretch`, so "where
// is this layer playing" has two answers, one, or none. These pin the arithmetic
// that works that out from the schedule, which is all layerPlayheads has to go
// on — there is no per-source position to read back out of Web Audio.

/** Start a mix and freeze its scheduler, so `currentTime` is the only clock. */
async function playing(layer) {
    const mixer = stubbedMixer();
    await mixer.setLayers([layer]);
    await mixer.play();
    // The real scheduler would fire on a timer and advance the schedule under
    // the test; here the test moves time itself.
    globalThis.clearInterval(mixer._timer);
    return mixer;
}

const at = (mixer, time) => {
    mixer.context.currentTime = time;
    return mixer.layerPlayheads(0).map((seconds) => Math.round(seconds * 1000) / 1000);
};

test("nothing is playing before play(), or on a layer with no audio", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav" }, { id: "blank", url: "" }]);
    assert.deepEqual(mixer.layerPlayheads(0), []);
    await mixer.play();
    globalThis.clearInterval(mixer._timer);
    assert.deepEqual(mixer.layerPlayheads(1), [], "a blank layer never sounds");
    assert.deepEqual(mixer.layerPlayheads(9), [], "and neither does a layer that is not there");
    mixer.destroy();
});

test("each pass reports where it is, and only while it is sounding", async () => {
    // A 24s file at the default 1.75 stretch: a 42s period, B trailing A by 21s.
    const mixer = await playing({ id: "a", url: "a.wav" });

    // A began at 0.08 and is the only pass running; B has not started yet.
    assert.deepEqual(at(mixer, 5), [4.92]);
    // A has run off the end of the file, and B is 8.92s into its own pass.
    assert.deepEqual(at(mixer, 30), [8.92]);
    // Both are in their region at once — the overlap the stretch is there for.
    assert.deepEqual(at(mixer, 22), [21.92, 0.92]);
    mixer.destroy();
});

test("stretched far enough apart, the passes leave real silence between them", async () => {
    // At 1.75 the two passes overlap and the layer never stops. Stretch them to
    // 4 and B does not begin until long after A has run off the end of the file.
    const mixer = await playing({ id: "a", url: "a.wav", stretch: 4 });

    assert.deepEqual(at(mixer, 20), [19.92]);
    assert.deepEqual(at(mixer, 30), [], "nothing is sounding, so nothing is drawn");
    assert.deepEqual(at(mixer, 60), [11.92]);
    mixer.destroy();
});

test("a crossfading schedule sounds twice over while the seam runs", async () => {
    // 24s of file, no drift and a 3s crossfade: A repeats every 21s, so from
    // 21.08 the outgoing pass runs its last three seconds under the new one.
    const mixer = await playing({ id: "a", url: "a.wav", stretch: 1, loop_crossfade: 3 });

    // A's outgoing pass at its tail, A's arriving pass at its head, then B.
    assert.deepEqual(at(mixer, 22), [21.92, 0.92, 9.92]);
    // Three seconds on the seam is over and A is down to one head again.
    assert.deepEqual(at(mixer, 25), [3.92, 12.92]);
    mixer.destroy();
});

test("a playhead never leaves the crop it is playing", async () => {
    const mixer = await playing({ id: "a", url: "a.wav", trimStart: 4, trimEnd: 10 });

    for (let time = 0; time < 60; time += 0.25) {
        for (const head of at(mixer, time)) {
            assert.ok(head >= 4 && head <= 10, `head at ${head}s escaped the 4–10s crop`);
        }
    }
    mixer.destroy();
});

test("a playhead crosses the file as fast as the layer is played", async () => {
    const mixer = await playing({ id: "a", url: "a.wav", playbackRate: 2 });

    // Twice the rate is twice the distance covered per second of wall time.
    assert.deepEqual(at(mixer, 5), [9.84]);
    mixer.destroy();
});

test("pausing holds the playheads where they are", async () => {
    const mixer = await playing({ id: "a", url: "a.wav" });

    const before = at(mixer, 5);
    // Suspending the context is what pause() does, and it stops currentTime —
    // so reading the schedule against it needs no pause handling of its own.
    await mixer.pause();
    assert.deepEqual(at(mixer, 5), before);
    mixer.destroy();
});

// A baked loop and the timing a mix wraps around it: back to back, one copy or
// two, cycles with a rest, a start delay, and phase shifting. Where every pass
// begins is arithmetic on its number (_startA / _startB), so these read it
// straight off the voice as well as off what the scheduler queued.

/** Advance the clock and let the scheduler queue what is now due. */
function tickTo(mixer, time) {
    mixer.context.currentTime = time;
    mixer._tick();
}

// `+ 0` turns the -0 a float hair under zero rounds to back into 0.
const round = (seconds) => Math.round(seconds * 1000) / 1000 + 0;

test("spacing 1 keeps a loop's exact length, so it butts against itself", () => {
    const butted = timingForBuffers(7.3, 7.3, { stretch: 1 });
    assert.equal(butted.period, 7.3, "not 7.25: the join would overlap");
    assert.equal(butted.offsetB, 3.65);
    // Every other spacing keeps the eighth-second rounding it always had.
    assert.equal(timingForBuffers(7.3, 7.3).period, roundToEighth(7.3) * 1.75);
});

test("one copy schedules no second pass", async () => {
    const starts = [];
    const mixer = stubbedMixer(starts);
    await mixer.setLayers([{ id: "a", url: "a.wav", stretch: 1, second_copy: false }]);
    await mixer.play();
    globalThis.clearInterval(mixer._timer);

    tickTo(mixer, 30);
    mixer.destroy();

    assert.deepEqual(starts.map(([when]) => round(when)), [0.08, 24.08]);
});

test("two copies at spacing 1 interleave B half a pass behind A", async () => {
    const starts = [];
    const mixer = stubbedMixer(starts);
    await mixer.setLayers([{ id: "a", url: "a.wav", stretch: 1 }]);
    await mixer.play();
    globalThis.clearInterval(mixer._timer);

    tickTo(mixer, 30);
    mixer.destroy();

    assert.deepEqual(starts.map(([when]) => round(when)), [0.08, 24.08, 12.08]);
});

test("a cycle is its repetitions, then its rest", async () => {
    const starts = [];
    const mixer = stubbedMixer(starts);
    await mixer.setLayers([{
        id: "a", url: "a.wav", stretch: 1, second_copy: false,
        repetitions: 2, cycle_rest: 10,
    }]);
    await mixer.play();
    globalThis.clearInterval(mixer._timer);

    tickTo(mixer, 120);
    mixer.destroy();

    assert.deepEqual(
        starts.map(([when]) => round(when)),
        [0.08, 24.08, 58.08, 82.08, 116.08],
        "two back to back, ten seconds of nothing, two more",
    );
});

test("repetitions mean nothing without a rest", async () => {
    const plain = stubbedMixer();
    const counted = stubbedMixer();
    await plain.setLayers([{ id: "a", url: "a.wav" }]);
    await counted.setLayers([{ id: "a", url: "a.wav", repetitions: 3 }]);

    for (let k = 0; k < 8; k += 1) {
        assert.equal(counted._startA(counted.voices[0], k), plain._startA(plain.voices[0], k));
        assert.equal(counted._startB(counted.voices[0], k), plain._startB(plain.voices[0], k));
    }
    plain.destroy();
    counted.destroy();
});

test("a start delay holds back the first pass", async () => {
    const starts = [];
    const mixer = stubbedMixer(starts);
    await mixer.setLayers([{ id: "a", url: "a.wav", start_delay: 5 }]);
    await mixer.play();
    globalThis.clearInterval(mixer._timer);

    assert.deepEqual(starts, [], "nothing is due before the delay runs out");
    tickTo(mixer, 5);
    assert.deepEqual(starts.map(([when]) => round(when)), [5.08]);
    mixer.destroy();
});

test("a settings rebuild restarts at once unless the delay itself changed", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{ id: "a", url: "a.wav", start_delay: 5 }]);
    mixer.context.currentTime = 10;

    await mixer.replaceLayer(0, { id: "a", url: "a.wav", start_delay: 5, stretch: 2 });
    assert.equal(round(mixer.voices[0].t0), 10.08, "a spacing change is heard straight away");

    await mixer.replaceLayer(0, { id: "a", url: "a.wav", start_delay: 5 }, { delayStart: true });
    assert.equal(round(mixer.voices[0].t0), 15.08, "a new delay is heard as a delay");
    mixer.destroy();
});

test("a rest is silence on the playheads too", async () => {
    const mixer = await playing({
        id: "a", url: "a.wav", stretch: 1, second_copy: false, cycle_rest: 10,
    });

    assert.deepEqual(at(mixer, 20), [19.92]);
    assert.deepEqual(at(mixer, 30), [], "between 24.08 and 34.08 the layer rests");
    assert.deepEqual(at(mixer, 35), [0.92]);
    mixer.destroy();
});

test("phase shifts alternate between the two holds", () => {
    // Hold 2, then 3, then 2: shifts land before passes 2, 5, 7, 10 ...
    assert.deepEqual(
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((k) => shiftsBefore(k, 2, 3)),
        [0, 0, 1, 1, 1, 2, 2, 3, 3, 3, 4],
    );
});

test("B slips a step later at every shift, and stays there", async () => {
    const mixer = stubbedMixer();
    // 24s back to back: A every 24s, B 12s behind; a step is 3s.
    await mixer.setLayers([{
        id: "a", url: "a.wav", stretch: 1,
        phase_step: 0.125, phase_hold: 2, phase_hold_alt: 3,
    }]);
    const voice = mixer.voices[0];
    const lag = (k) => round(mixer._startB(voice, k) - mixer._startA(voice, k));

    assert.deepEqual([0, 1, 2, 3, 4, 5, 6].map(lag), [12, 12, 15, 15, 15, 18, 18]);
    mixer.destroy();
});

test("the slip wraps inside the period, dropping the pass where it comes round", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{
        id: "a", url: "a.wav", stretch: 1,
        phase_step: 0.25, phase_hold: 2, phase_hold_alt: 2,
    }]);
    const voice = mixer.voices[0];
    const lag = (k) => {
        const when = mixer._startB(voice, k);
        return when == null ? null : round(when - mixer._startA(voice, k));
    };

    // 12s behind, 18, then 24 is a whole period: that pass is dropped and B
    // carries on in unison with A, then 6s behind, and round again.
    assert.deepEqual([0, 1, 2, 3, 4, 5, 6, 7].map(lag), [12, 12, 18, 18, null, 0, 6, 6]);
    for (let k = 0; k < 40; k += 1) {
        const when = mixer._startB(voice, k);
        if (when == null) continue;
        assert.ok(when < mixer._startA(voice, k + 1), `B pass ${k} left its period`);
    }
    mixer.destroy();
});

test("the shift count runs through rests, so a shift can land mid-cycle", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{
        id: "a", url: "a.wav", stretch: 1, repetitions: 2, cycle_rest: 10,
        phase_step: 0.125, phase_hold: 3, phase_hold_alt: 3,
    }]);
    const voice = mixer.voices[0];
    const lag = (k) => round(mixer._startB(voice, k) - mixer._startA(voice, k));

    // Passes 2 and 3 are the second cycle; the shift falls between them.
    assert.equal(lag(2), 12);
    assert.equal(lag(3), 15);
    mixer.destroy();
});

test("a seamless loop is only de-clicked where it does not butt", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([
        { id: "butted", url: "a.wav", seamless: true, stretch: 1, second_copy: false },
        { id: "rested", url: "a.wav", seamless: true, stretch: 1, second_copy: false, cycle_rest: 5 },
        { id: "older", url: "a.wav", stretch: 1, second_copy: false, cycle_rest: 5 },
    ]);
    const [butted, rested, older] = mixer.voices;

    assert.deepEqual(mixer._edges(butted, "A", 0), { fadeIn: true, fadeOut: false });
    assert.deepEqual(mixer._edges(butted, "A", 1), { fadeIn: false, fadeOut: false });
    assert.deepEqual(mixer._edges(rested, "A", 1), { fadeIn: true, fadeOut: true });
    assert.equal(mixer._edges(older, "A", 1), null, "an unbaked file plays as it always has");
    mixer.destroy();
});

test("a de-clicked pass ramps its unbutted edges on a node of its own", async () => {
    const mixer = stubbedMixer();
    await mixer.setLayers([{
        id: "a", url: "a.wav", seamless: true, stretch: 1, second_copy: false, cycle_rest: 5,
    }]);
    await mixer.play();
    globalThis.clearInterval(mixer._timer);
    const ramps = mixer.context.gains.filter((node) => node.gain.events.some(
        (event) => event.type === "ramp" && event.value === 0,
    ));
    mixer.destroy();

    assert.equal(ramps.length, 1, "the one pass queued so far");
    const events = ramps[0].gain.events.map(({ type, value, when }) => [type, value, round(when)]);
    assert.deepEqual(events, [
        ["set", 0, 0.08],
        ["ramp", 1, 0.09],
        ["set", 1, 24.07],
        ["ramp", 0, 24.08],
    ]);
});

test("make-up gain stops where the loudest sample would pass the ceiling", async () => {
    const mixer = new SoundscapeMixer({ audioContext: fakeContext() });
    const tone = toneBuffer({ lufs: -20 });
    const samples = tone.getChannelData(0);
    samples[1000] = 0.9;
    mixer._decode = async () => tone;
    await mixer.setLayers([{ id: "a", url: "a.wav", level: 1 }]);

    const analysis = mixer.setLayerLoudness(0, -14);

    assert.equal(analysis.loudnessLimit, "peak");
    assert.ok(Math.abs(analysis.loudnessPeakDb - 20 * Math.log10(0.9)) < 1e-6);
    assert.ok(Math.abs(analysis.loudnessGainDb - (PEAK_CEILING_DB - 20 * Math.log10(0.9))) < 1e-6);
    mixer.destroy();
});

test("a very quiet source names the gain cap as what held it back", async () => {
    const mixer = new SoundscapeMixer({ audioContext: fakeContext() });
    mixer._decode = async () => toneBuffer({ lufs: -50 });
    await mixer.setLayers([{ id: "a", url: "a.wav", level: 1 }]);

    const analysis = mixer.setLayerLoudness(0, -20);

    assert.equal(analysis.loudnessLimit, "gain");
    assert.equal(analysis.loudnessGainDb, 24);
    mixer.destroy();
});

// ---------------------------------------------------------------------------
// Handing a layer over in place: retimeLayer and seekLayer.
// ---------------------------------------------------------------------------

/** A playing one-copy loop over a 24s file, with its sources caught. */
async function handingOver(layer = {}) {
    const starts = [];
    const sources = [];
    const mixer = stubbedMixer(starts);
    const create = mixer.context.createBufferSource;
    mixer.context.createBufferSource = () => {
        const source = create();
        sources.push(source);
        return source;
    };
    const base = { id: "a", url: "a.wav", stretch: 1, second_copy: false, ...layer };
    await mixer.setLayers([base]);
    await mixer.play();
    globalThis.clearInterval(mixer._timer);
    return { mixer, starts, sources, base };
}

const startsFrom = (starts, from) => starts.slice(from).map((args) => args.map(round));

test("a settings change carries on from where the layer was", async () => {
    const { mixer, starts, base } = await handingOver();
    tickTo(mixer, 10);
    const before = starts.length;

    await mixer.retimeLayer(0, { ...base, loop_crossfade: 1 });

    // Pass 0 began at 0.08, so at the handoff (10.03) it is 9.95s in, and the
    // rebuilt voice joins it right there instead of starting it again.
    assert.equal(round(mixer.voices[0].t0), 0.08);
    assert.deepEqual(startsFrom(starts, before), [[10.03, 9.95, 14.05]]);
    mixer.destroy();
});

test("a new rate keeps the place in the file and changes the pitch of it", async () => {
    const { mixer, starts, sources, base } = await handingOver();
    tickTo(mixer, 10);
    const before = starts.length;

    await mixer.retimeLayer(0, { ...base, playbackRate: 2 });

    assert.deepEqual(startsFrom(starts, before), [[10.03, 9.95, 14.05]]);
    assert.equal(sources.at(-1).playbackRate.value, 2);
    // What is left of the file now takes half as long, so the next pass
    // comes round at 10.03 + 14.05 / 2.
    assert.equal(round(mixer._startA(mixer.voices[0], 1)), 17.055);
    mixer.destroy();
});

test("the old voice hands over in a blink rather than a crossfade", async () => {
    const { mixer, base } = await handingOver();
    tickTo(mixer, 10);
    const previous = mixer.voices[0];

    await mixer.retimeLayer(0, { ...base, stretch: 2 });

    const fade = previous.gain.gain.events.at(-1);
    assert.equal(fade.value, 0);
    assert.equal(round(fade.when), 10.07, "out by the end of the handoff");
    mixer.destroy();
});

test("a pass joined part-way fades in over the handoff", async () => {
    const { mixer, sources, base } = await handingOver();
    tickTo(mixer, 10);

    await mixer.retimeLayer(0, { ...base, stretch: 1.5 });

    const [entry] = sources.at(-1).connections;
    assert.deepEqual(
        entry.gain.events.map(({ value, when }) => [value, round(when)]),
        [[0, 10.03], [1, 10.07]],
    );
    mixer.destroy();
});

test("seeking plays the pass from there, and the next one comes round after it", async () => {
    const { mixer, starts } = await handingOver();
    tickTo(mixer, 10);
    const before = starts.length;

    await mixer.seekLayer(0, 20);
    assert.deepEqual(startsFrom(starts, before), [[10.03, 20, 4]]);

    tickTo(mixer, 13.8);
    assert.deepEqual(startsFrom(starts, before + 1), [[14.03, 0, 24]]);
    mixer.destroy();
});

test("a seek is kept inside the kept region", async () => {
    const { mixer, starts } = await handingOver({ trim_start: 4, trim_end: 16 });
    tickTo(mixer, 2);
    const before = starts.length;

    await mixer.seekLayer(0, 1);
    assert.deepEqual(startsFrom(starts, before), [[2.03, 4, 12]], "from the start marker");
    mixer.destroy();
});

test("seeking into a seam joins both sides of the crossfade half-way", async () => {
    // 24s passes fading over 2s, so a pass comes round every 22s and its last
    // 2s sound over the next one's first 2s.
    const { mixer, starts, sources } = await handingOver({ loop_crossfade: 2 });
    tickTo(mixer, 10);
    const before = starts.length;
    const sourcesBefore = sources.length;

    await mixer.seekLayer(0, 23);

    assert.deepEqual(startsFrom(starts, before), [
        [10.03, 23, 1], // the tail, a second from its end
        [10.03, 1, 23], // the next head, a second into it
    ]);
    const [tail, head] = sources.slice(sourcesBefore)
        .map((source) => source.connections[0].connections[0].gain.curves);
    // Each carries on from the middle of its equal-power ramp, not the top.
    assert.equal(tail.length, 1);
    assert.equal(round(tail[0].when), 10.03);
    assert.equal(round(tail[0].duration), 1);
    assert.ok(Math.abs(tail[0].curve[0] - Math.SQRT1_2) < 1e-6, "falling from half-way");
    assert.equal(round(head[0].duration), 1);
    assert.ok(Math.abs(head[0].curve[0] - Math.SQRT1_2) < 1e-6, "rising from half-way");
    // The head's own tail is still to come, in full.
    assert.equal(round(head[1].when), 31.03);
    assert.equal(round(head[1].duration), 2);
    mixer.destroy();
});

test("a crop that now ends behind the playhead starts the next pass at once", async () => {
    const { mixer, starts, base } = await handingOver();
    tickTo(mixer, 10);
    const before = starts.length;

    await mixer.retimeLayer(0, { ...base, trim_end: 6 });

    assert.deepEqual(startsFrom(starts, before), [[10.03, 0, 6]]);
    mixer.destroy();
});

test("during its start delay a layer keeps waiting, against the new delay", async () => {
    const mixer = stubbedMixer();
    const layer = { id: "a", url: "a.wav", start_delay: 5 };
    await mixer.setLayers([layer]);
    await mixer.play();
    globalThis.clearInterval(mixer._timer);
    mixer.context.currentTime = 2;

    await mixer.retimeLayer(0, { ...layer, stretch: 2 });
    assert.equal(round(mixer.voices[0].t0), 5.08, "a spacing change does not restart the wait");

    await mixer.retimeLayer(0, { ...layer, start_delay: 8 });
    assert.equal(round(mixer.voices[0].t0), 8.08, "the wait is measured from the start");
    mixer.destroy();
});

// ---------------------------------------------------------------------------
// Two pitches: the second copy's own rate, and taking turns.
// ---------------------------------------------------------------------------

test("a second rate plays the second copy at its own pitch", async () => {
    const { mixer, sources } = await handingOver({
        stretch: 1.75, second_copy: true, playbackRate: 1, playback_rate_b: 0.5,
    });
    tickTo(mixer, 60);

    const rates = new Set(sources.map((source) => source.playbackRate.value));
    assert.deepEqual([...rates].sort(), [0.5, 1]);
    mixer.destroy();
});

test("without a second rate the copies share one, and the schedule is as it was", () => {
    assert.deepEqual(
        timingForBuffers(24, 24, { playbackRate: 2 }),
        timingForBuffers(24, 24, { playbackRate: 2, playbackRateB: 2 }),
    );
    assert.deepEqual(timingForBuffers(24, 24, { playbackRateB: null }), timingForBuffers(24, 24));
});

test("taking turns: B after A has finished, A after B, a gap between every turn", async () => {
    // 24s at 1× is 24s heard; at 0.5× it is 48s. With a 3s gap a round is
    // 24 + 3 + 48 + 3 = 78s.
    const { mixer, starts } = await handingOver({
        second_copy: true, playbackRate: 1, playback_rate_b: 0.5,
        take_turns: true, turn_gap: 3, stretch: 1.75,
    });
    const voice = mixer.voices[0];
    assert.equal(round(voice.period), 78);
    assert.equal(round(voice.offsetB), 27);

    tickTo(mixer, 200);
    const turns = starts.map(([when]) => round(when)).sort((a, b) => a - b);
    assert.deepEqual(turns, [0.08, 27.08, 78.08, 105.08, 156.08, 183.08]);
    // Nothing ever sounds over anything else.
    assert.deepEqual(at(mixer, 20), [19.92]);
    assert.deepEqual(at(mixer, 26), [], "the gap after A");
    assert.equal(at(mixer, 30).length, 1, "B alone");
    mixer.destroy();
});

test("taking turns ignores the spacing and never slips B into A's turn", async () => {
    const plain = await handingOver({ second_copy: true, take_turns: true, turn_gap: 2 });
    const odd = await handingOver({
        second_copy: true, take_turns: true, turn_gap: 2, stretch: 3, phase_step: 0.25, phase_hold: 1,
    });
    for (let k = 0; k < 6; k += 1) {
        assert.equal(odd.mixer._startB(odd.mixer.voices[0], k), plain.mixer._startB(plain.mixer.voices[0], k));
    }
    plain.mixer.destroy();
    odd.mixer.destroy();
});

test("taking turns needs a second copy to take turns with", async () => {
    const { mixer } = await handingOver({ second_copy: false, take_turns: true, turn_gap: 5 });
    assert.equal(round(mixer.voices[0].period), 24, "one copy, back to back as before");
    mixer.destroy();
});
