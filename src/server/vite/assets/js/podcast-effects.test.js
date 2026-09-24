import test from "node:test";
import assert from "node:assert/strict";
import { createPodcastEffectsGraph, DEFAULT_PODCAST_EFFECTS, getPodcastPreset, PODCAST_PRESETS } from "./podcast-effects.js";

function fixture(options = {}) {
    const nodes = [];
    const buffers = [];
    const parameter = (value = 0) => ({
        value, ramps: [],
        cancelScheduledValues() {},
        setValueAtTime(next) { this.value = next; },
        linearRampToValueAtTime(next, time) { this.value = next; this.ramps.push({ value: next, time }); },
    });
    const node = (kind) => {
        const item = {
            kind, connections: [], starts: 0, stops: 0,
            connect(target) { this.connections.push(target); },
            disconnect() { this.connections = []; },
            start() { this.starts += 1; },
            stop() { this.stops += 1; },
        };
        for (const property of ["gain", "frequency", "Q", "delayTime", "threshold", "ratio", "knee", "attack", "release"]) {
            item[property] = parameter(property === "gain" ? 1 : 0);
        }
        nodes.push(item);
        return item;
    };
    const context = {
        currentTime: 2,
        sampleRate: 22050,
        createGain: () => node("gain"),
        createBiquadFilter: () => node("filter"),
        createDynamicsCompressor: () => node("compressor"),
        createWaveShaper: () => node("shaper"),
        createDelay: (maxDelayTime) => Object.assign(node("delay"), { maxDelayTime }),
        createConvolver: () => node("convolver"),
        createOscillator: () => node("oscillator"),
        createBufferSource: () => node("noise"),
        createBuffer(channels, length, sampleRate) {
            const data = Array.from({ length: channels }, () => new Float32Array(length));
            const result = { length, sampleRate, duration: length / sampleRate, getChannelData: (channel) => data[channel] };
            buffers.push(result);
            return result;
        },
    };
    const source = node("source");
    const destination = node("destination");
    return {
        context, source, destination, nodes, buffers,
        create: () => createPodcastEffectsGraph(context, source, destination, options),
        inspect() {
            const [dry, input] = source.connections;
            const high = input.connections[0];
            const low = high.connections[0];
            const tone = low.connections[0];
            const compressor = tone.connections[0];
            const drive = compressor.connections[0];
            const shaper = drive.connections[0];
            const compensation = shaper.connections[0];
            const delay = compensation.connections[0];
            const tremolo = delay.connections[0];
            const [wet, roomDelay] = tremolo.connections;
            const room = roomDelay.connections[0].connections[0];
            const roomGain = room.connections[0];
            const gate = roomGain.connections[0];
            return { dry, input, high, low, tone, compressor, drive, shaper, compensation, delay, tremolo, wet, roomDelay, room, roomGain, gate };
        },
    };
}

test("Original and a zero effect mix have exactly one audible, unchanged path", () => {
    for (const preset of ["clean", "noir", "shortwave"]) {
        const f = fixture({ preset, effectMix: preset === "clean" ? 1 : 0, texture: 1, space: 1 });
        const graph = f.create();
        graph.setPlaybackActive(true);
        const { dry, wet, roomGain, gate } = f.inspect();
        assert.equal(dry.gain.value, 1);
        assert.deepEqual(dry.connections, [f.destination]);
        assert.equal(wet.gain.value, 0);
        assert.equal(roomGain.gain.value, 0);
        assert.equal(gate.gain.value, 0);
        assert.equal(f.nodes.filter((node) => node.kind === "noise").length, 0);
        graph.destroy();
    }
});

test("dry, treated, and room gains partition unity with bounded controls", () => {
    const f = fixture({ preset: "noir" });
    const graph = f.create();
    for (const effectMix of [-9, 0, 0.25, 0.75, 1, 9]) {
        for (const space of [-2, 0, 0.7, 1, 2]) {
            graph.update({ effectMix, space, texture: 0 });
            const { dry, wet, roomGain } = f.inspect();
            assert.ok(Math.abs(dry.gain.value + wet.gain.value + roomGain.gain.value - 1) < 1e-12);
            assert.ok(dry.gain.value >= 0 && wet.gain.value >= 0);
            assert.ok(roomGain.gain.value >= 0 && roomGain.gain.value <= 0.2);
            assert.ok(wet.gain.ramps.every(({ time }) => time === 2.035));
        }
    }
    graph.destroy();
});

test("presets change physical filtering, dynamics, mono character and modulation without rebuilding", () => {
    const f = fixture({ texture: 0 });
    const graph = f.create();
    const nodeCount = f.nodes.length;
    const signatures = new Set();
    const { input, high, low, tone, compressor, drive, compensation, delay, tremolo } = f.inspect();
    for (const { id } of PODCAST_PRESETS) {
        graph.update({ preset: id });
        signatures.add([high.frequency.value, low.frequency.value, tone.frequency.value, tone.gain.value,
            drive.gain.value, compressor.threshold.value, compressor.ratio.value, delay.delayTime.value, tremolo.gain.value].join(":"));
        assert.ok(high.frequency.value < low.frequency.value);
        assert.ok(low.frequency.value < f.context.sampleRate / 2);
        assert.ok(compressor.ratio.value >= 1 && compressor.ratio.value <= 5);
        assert.ok(drive.gain.value * compensation.gain.value <= 1);
        if (["gramophone", "telephone", "radio", "newsreel", "shortwave"].includes(id)) assert.equal(input.channelCount, 1);
        if (id === "muffled") assert.ok(low.frequency.value < 1000);
        if (id === "telephone") assert.ok(high.frequency.value >= 300 && low.frequency.value <= 3400);
    }
    assert.equal(signatures.size, PODCAST_PRESETS.length);
    assert.equal(f.nodes.length, nodeCount);
    const shaper = f.inspect().shaper;
    assert.equal(shaper.curve[(shaper.curve.length - 1) / 2], 0);
    for (let i = 0; i < shaper.curve.length; i += 1) {
        assert.ok(Math.abs(shaper.curve[i]) <= 1);
        assert.equal(shaper.curve[i], -shaper.curve[shaper.curve.length - i - 1] || 0);
        if (i > 0) assert.ok(shaper.curve[i] >= shaper.curve[i - 1]);
    }
    graph.destroy();
});

test("tape and radio modulation remain in safe delay and gain ranges", () => {
    const f = fixture({ preset: "cassette" });
    const graph = f.create();
    const { delay, tremolo } = f.inspect();
    const [wow, flutter, fading] = f.nodes.filter((node) => node.kind === "oscillator").map((node) => node.connections[0]);
    assert.ok(wow.gain.value > 0 && flutter.gain.value > 0);
    assert.ok(delay.delayTime.value - wow.gain.value - flutter.gain.value > 0);
    assert.ok(delay.delayTime.value + wow.gain.value + flutter.gain.value < delay.maxDelayTime);
    graph.update({ preset: "shortwave" });
    assert.equal(wow.gain.value, 0);
    assert.equal(flutter.gain.value, 0);
    assert.ok(fading.gain.value > 0);
    assert.ok(tremolo.gain.value - fading.gain.value > 0.8);
    assert.ok(tremolo.gain.value + fading.gain.value <= 1);
    graph.destroy();
});

test("generated textures are finite, quiet and sparse, and all generators stop on teardown", () => {
    const f = fixture({ preset: "gramophone", effectMix: 1, texture: 1, space: 1 });
    const graph = f.create();
    assert.equal(f.buffers.length, 1);
    assert.ok(f.buffers[0].duration <= 0.4);
    graph.setPlaybackActive(true);
    const noises = f.nodes.filter((node) => node.kind === "noise");
    assert.equal(noises.length, 2);
    const [hiss, crackle] = noises.map((node) => node.buffer.getChannelData(0));
    assert.ok(hiss.some((sample) => Math.abs(sample) > 0.1));
    assert.ok(Math.abs(hiss.reduce((sum, sample) => sum + sample, 0) / hiss.length) < 0.01);
    assert.ok(crackle.some((sample) => Math.abs(sample) > 0.1));
    assert.ok(crackle.filter((sample) => Math.abs(sample) > 0.01).length / crackle.length < 0.03);
    for (const buffer of f.buffers) {
        assert.ok(buffer.getChannelData(0).every((sample) => Number.isFinite(sample) && Math.abs(sample) <= 1));
    }
    graph.setPlaybackActive(false);
    assert.equal(f.inspect().gate.gain.value, 0);
    assert.ok(noises.every((node) => node.stops === 1 && node.connections.length === 0));
    graph.setPlaybackActive(true);
    assert.equal(f.buffers.length, 3, "buffers are reused across pauses");
    graph.update({ texture: 0 });
    assert.ok(f.nodes.filter((node) => node.kind === "noise").every((node) => node.stops === 1));
    graph.destroy();
    graph.destroy();
    graph.update({ texture: 1 });
    graph.setPlaybackActive(true);
    assert.ok(f.nodes.every((node) => node.connections.length === 0));
    assert.ok(f.nodes.filter((node) => ["oscillator", "noise"].includes(node.kind)).every((node) => node.stops === 1));
});

test("partial construction failures clean up already running oscillators and connections", () => {
    const f = fixture();
    const factory = f.context.createOscillator;
    let count = 0;
    f.context.createOscillator = () => {
        if (++count === 3) throw new Error("no more oscillators");
        return factory();
    };
    assert.throws(() => f.create(), /no more oscillators/);
    assert.ok(f.nodes.every((node) => node.connections.length === 0));
    assert.ok(f.nodes.filter((node) => node.kind === "oscillator").every((node) => node.stops === 1));
});

test("unknown presets resolve to Original and nonfinite controls stay bounded", () => {
    assert.equal(getPodcastPreset("untrusted-preset").id, "clean");
    assert.equal(Object.isFrozen(DEFAULT_PODCAST_EFFECTS), true);
    assert.ok(PODCAST_PRESETS.every((preset) => preset.name && preset.description && preset.tag && preset.textureLabel));
    const f = fixture({ preset: "noir", effectMix: NaN, texture: Infinity, space: -Infinity });
    const graph = f.create();
    const { dry, wet, roomGain } = f.inspect();
    assert.equal(dry.gain.value, 1 - DEFAULT_PODCAST_EFFECTS.effectMix);
    assert.ok(Number.isFinite(wet.gain.value));
    assert.ok(Number.isFinite(roomGain.gain.value));
    graph.update({ preset: "__proto__" });
    assert.equal(dry.gain.value, 1);
    graph.destroy();
});
