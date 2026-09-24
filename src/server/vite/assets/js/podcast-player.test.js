import test from "node:test";
import assert from "node:assert/strict";
import { PodcastPlayer } from "./podcast-player.js";

const EPISODE = { audio_url: "https://publisher.example/episode.mp3" };

function deferred() {
    let resolve;
    let reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    return { promise, resolve, reject };
}

function fakeNode(kind) {
    const parameter = (value = 0) => ({
        value,
        cancelScheduledValues() {},
        setValueAtTime(next) { this.value = next; },
        linearRampToValueAtTime(next) { this.value = next; },
    });
    return {
        kind,
        gain: parameter(1),
        frequency: parameter(),
        Q: parameter(),
        delayTime: parameter(),
        threshold: parameter(),
        ratio: parameter(),
        knee: parameter(),
        attack: parameter(),
        release: parameter(),
        starts: 0,
        stops: 0,
        connections: [],
        disconnects: 0,
        start() { this.starts += 1; },
        stop() { this.stops += 1; },
        connect(node) { this.connections.push(node); },
        disconnect() { this.connections = []; this.disconnects += 1; },
    };
}

function fixture(options = {}) {
    const audios = [];
    const nodes = [];
    const snapshots = [];
    const timers = new Map();
    const calls = [];
    let timerId = 0;
    let ended = 0;
    const context = {
        state: "suspended",
        currentTime: 0,
        sampleRate: 22050,
        destination: fakeNode("destination"),
        resume: () => { calls.push("resume"); context.state = "running"; return Promise.resolve(); },
        close: () => { calls.push("close"); context.state = "closed"; return Promise.resolve(); },
        createMediaElementSource: () => { const node = fakeNode("source"); nodes.push(node); return node; },
        createGain: () => { const node = fakeNode("gain"); nodes.push(node); return node; },
        createBiquadFilter: () => { const node = fakeNode("biquad"); nodes.push(node); return node; },
        createWaveShaper: () => { const node = fakeNode("shaper"); nodes.push(node); return node; },
        createDynamicsCompressor: () => { const node = fakeNode("compressor"); nodes.push(node); return node; },
        createDelay: () => { const node = fakeNode("delay"); nodes.push(node); return node; },
        createConvolver: () => { const node = fakeNode("convolver"); nodes.push(node); return node; },
        createOscillator: () => { const node = fakeNode("oscillator"); nodes.push(node); return node; },
        createBufferSource: () => { const node = fakeNode("noise"); nodes.push(node); return node; },
        createBuffer(channels, length, sampleRate) {
            const data = Array.from({ length: channels }, () => new Float32Array(length));
            return { length, sampleRate, numberOfChannels: channels, getChannelData: (channel) => data[channel] };
        },
    };
    const audioFactory = () => {
        const listeners = new Map();
        const audio = {
            listeners,
            paused: true,
            readyState: 0,
            currentTime: 0,
            duration: NaN,
            volume: 1,
            src: "",
            crossOrigin: null,
            loads: 0,
            pauses: 0,
            playCalls: 0,
            addEventListener(event, fn) { listeners.set(event, fn); },
            removeEventListener(event, fn) { if (listeners.get(event) === fn) listeners.delete(event); },
            emit(event) { listeners.get(event)?.(); },
            play() {
                calls.push("play");
                this.playCalls += 1;
                if (this.playImpl) return this.playImpl();
                this.paused = false;
                this.emit("playing");
                return Promise.resolve();
            },
            pause() { this.paused = true; this.pauses += 1; },
            load() { this.loads += 1; },
            removeAttribute(name) { if (name === "src") this.src = ""; },
        };
        audios.push(audio);
        return audio;
    };
    const player = new PodcastPlayer({
        audioFactory,
        audioContextFactory: () => context,
        onChange: (snapshot) => snapshots.push(snapshot),
        onEnded: () => { ended += 1; },
        scheduleTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id; },
        cancelTimeout(id) { timers.delete(id); },
        ...options,
    });
    return {
        player, audios, nodes, context, calls, snapshots, timers,
        get state() { return snapshots.at(-1); },
        get ended() { return ended; },
        expire() {
            const [id, callback] = timers.entries().next().value;
            timers.delete(id);
            callback();
        },
    };
}

test("loading an episode defers its download and prepares direct publisher playback", async () => {
    const f = fixture();
    await f.player.load(EPISODE);
    const audio = f.audios[0];
    assert.equal(audio.src, EPISODE.audio_url);
    assert.equal(audio.preload, "none");
    assert.equal(audio.crossOrigin, "anonymous");
    assert.equal(audio.loads, 0);
    assert.equal(audio.playCalls, 0);
    assert.equal(f.timers.size, 0);
    assert.equal(f.state.effectsAvailable, true);
    assert.equal(f.state.loading, false);
    assert.equal(f.nodes.find((node) => node.kind === "gain").gain.value, 0.75);
    f.player.destroy();
});

test("autoplay unlocks context and starts media in the same synchronous gesture", async () => {
    const f = fixture();
    const resume = deferred();
    f.context.resume = () => { f.calls.push("resume"); return resume.promise; };
    const playback = f.player.load(EPISODE, { autoplay: true });
    assert.deepEqual(f.calls, ["resume", "play"]);
    resume.resolve();
    assert.equal(await playback, true);
    assert.equal(f.state.playing, true);
    assert.equal(f.state.loading, false);
    assert.equal(f.timers.size, 0);
    f.player.destroy();
});

test("presets change only the live graph and volume clamps to its allowed range", async () => {
    const f = fixture();
    await f.player.load(EPISODE, { preset: "radio", volume: 0.4 });
    const source = f.nodes.find((node) => node.kind === "source");
    const gain = f.nodes.find((node) => node.kind === "gain");
    const dry = source.connections[0];
    const input = source.connections[1];
    const highpass = input.connections[0];
    const lowpass = highpass.connections[0];
    const shaper = f.nodes.find((node) => node.kind === "shaper");
    const nodeCount = f.nodes.length;
    assert.equal(highpass.frequency.value, 280);
    f.player.setPreset("vintage");
    assert.equal(highpass.type, "highpass");
    assert.equal(highpass.frequency.value, 180);
    assert.equal(lowpass.type, "lowpass");
    assert.equal(lowpass.frequency.value, 3300);
    assert.equal(shaper.curve.length, 2049);
    assert.ok(shaper.curve.every((sample) => Math.abs(sample) <= 1));
    f.player.setPreset("muffled");
    assert.equal(lowpass.frequency.value, 850);
    f.player.setPreset("clean");
    assert.equal(dry.gain.value, 1);
    assert.equal(f.nodes.length, nodeCount);
    assert.equal(source.connections[1], input);
    f.player.setVolume(4);
    assert.equal(gain.gain.value, 1);
    f.player.setVolume(-1);
    assert.equal(gain.gain.value, 0);
    assert.equal(f.audios.length, 1);
    assert.equal(f.audios[0].playCalls, 0);
    f.player.destroy();
});

test("texture only runs during audible playback and releases every generated source", async () => {
    const f = fixture();
    await f.player.load(EPISODE, { preset: "gramophone", effectMix: 1, texture: 1, space: 1 });
    const audio = f.audios[0];
    const liveNoise = () => f.nodes.filter((node) => node.kind === "noise" && !node.stops);
    assert.equal(liveNoise().length, 0);
    await f.player.play();
    assert.equal(liveNoise().length, 2);
    audio.emit("waiting");
    assert.equal(liveNoise().length, 0);
    audio.emit("playing");
    assert.equal(liveNoise().length, 2);
    f.player.setVolume(0);
    assert.equal(liveNoise().length, 0);
    f.player.setVolume(0.7);
    assert.equal(liveNoise().length, 2);
    audio.muted = true;
    audio.emit("volumechange");
    assert.equal(liveNoise().length, 0);
    audio.muted = false;
    audio.volume = 0;
    audio.emit("volumechange");
    assert.equal(liveNoise().length, 0);
    audio.volume = 1;
    audio.emit("volumechange");
    assert.equal(liveNoise().length, 2);
    f.player.pause();
    assert.equal(liveNoise().length, 0);
    await f.player.play();
    audio.emit("ended");
    assert.equal(liveNoise().length, 0);
    f.player.destroy();
    for (const node of f.nodes.filter((entry) => ["noise", "oscillator"].includes(entry.kind))) {
        assert.equal(node.stops, 1);
        assert.equal(node.connections.length, 0);
    }
});

test("effect controls clamp, keep the media position, and Original disables all texture", async () => {
    const f = fixture();
    await f.player.load(EPISODE, { preset: "cassette", autoplay: true, effectMix: 0.6, texture: 0.8, space: 0.9 });
    const audio = f.audios[0];
    audio.currentTime = 84;
    const source = f.nodes.find((node) => node.kind === "source");
    const dry = source.connections[0];
    const liveNoise = () => f.nodes.filter((node) => node.kind === "noise" && !node.stops);
    assert.equal(dry.gain.value, 0.4);
    assert.equal(liveNoise().length, 2);
    f.player.setEffectMix(-2);
    assert.equal(dry.gain.value, 1);
    assert.equal(liveNoise().length, 0);
    f.player.setEffectMix(2);
    assert.equal(dry.gain.value, 0);
    f.player.setTexture(-2);
    assert.equal(liveNoise().length, 0);
    f.player.setTexture(2);
    assert.equal(liveNoise().length, 2);
    f.player.setSpace(Infinity);
    f.player.setPreset("clean");
    f.player.setTexture(1);
    f.player.setSpace(1);
    assert.equal(dry.gain.value, 1);
    assert.equal(liveNoise().length, 0);
    assert.equal(f.audios.length, 1);
    assert.equal(audio.currentTime, 84);
    assert.equal(audio.playCalls, 1);
    f.player.destroy();
});

test("source changes and CORS fallback stop texture and disconnect the entire graph", async () => {
    const f = fixture();
    await f.player.load(EPISODE, { preset: "shortwave", texture: 1, autoplay: true });
    const firstNodes = [...f.nodes];
    await f.player.load({ audio_url: "https://publisher.example/two.mp3" }, { preset: "cassette", texture: 1, autoplay: true });
    assert.ok(firstNodes.every((node) => node.connections.length === 0));
    assert.ok(firstNodes.filter((node) => ["noise", "oscillator"].includes(node.kind)).every((node) => node.stops === 1));
    f.audios[1].emit("error");
    assert.equal(f.state.effectsAvailable, false);
    assert.ok(f.nodes.every((node) => node.connections.length === 0));
    assert.ok(f.nodes.filter((node) => ["noise", "oscillator"].includes(node.kind)).every((node) => node.stops === 1));
    f.player.setTexture(1);
    f.player.setSpace(1);
    f.player.setEffectMix(1);
    assert.equal(f.audios.length, 3);
    f.player.destroy();
});

test("filter-enabled media errors retry a fresh plain stream at the same position", async () => {
    const f = fixture();
    await f.player.load(EPISODE, { autoplay: true, volume: 0.35 });
    const original = f.audios[0];
    original.currentTime = 92;
    original.emit("error");
    const fallback = f.audios[1];
    assert.equal(original.src, "");
    assert.equal(original.paused, true);
    assert.equal(original.listeners.size, 0);
    assert.equal(fallback.crossOrigin, null);
    assert.equal(fallback.volume, 0.35);
    assert.equal(fallback.playCalls, 1);
    fallback.readyState = 1;
    fallback.duration = 900;
    fallback.emit("loadedmetadata");
    assert.equal(fallback.currentTime, 92);
    assert.equal(f.state.effectsAvailable, false);
    assert.match(f.state.notice, /host or browser/);
    assert.doesNotMatch(f.state.notice, /CORS/);
    assert.equal(f.state.error, "");
    f.player.setVolume(0.2);
    assert.equal(fallback.volume, 0.2);
    f.player.setPreset("radio");
    assert.equal(f.audios.length, 2);
    f.player.destroy();
});

test("a paused episode's fallback stays paused", async () => {
    const f = fixture();
    await f.player.load(EPISODE);
    f.audios[0].currentTime = 41;
    f.audios[0].emit("error");
    assert.equal(f.audios.length, 2);
    assert.equal(f.audios[1].playCalls, 0);
    assert.equal(f.state.loading, false);
    assert.equal(f.state.playing, false);
    f.player.destroy();
});

test("plain stream errors produce an actionable error without repeated retries", async () => {
    const f = fixture();
    await f.player.load(EPISODE, { autoplay: true });
    f.audios[0].emit("error");
    const fallback = f.audios[1];
    fallback.emit("error");
    fallback.emit("error");
    assert.equal(f.audios.length, 2);
    assert.equal(f.state.effectsAvailable, false);
    assert.equal(f.state.playing, false);
    assert.equal(f.state.loading, false);
    assert.match(f.state.error, /unavailable or unsupported/);
    assert.equal(f.timers.size, 0);
    f.player.destroy();
});

test("unsupported Web Audio still streams with a clear filters notice", async () => {
    const f = fixture({ audioContextFactory: () => null });
    assert.equal(await f.player.load(EPISODE, { autoplay: true }), true);
    assert.equal(f.audios[0].crossOrigin, null);
    assert.equal(f.state.effectsAvailable, false);
    assert.match(f.state.notice, /unavailable in this browser/);
    f.player.destroy();
});

test("a graph construction failure discards its attached media element", async () => {
    const f = fixture();
    f.context.createGain = () => { throw new Error("unsupported graph"); };
    assert.equal(await f.player.load(EPISODE, { autoplay: true }), true);
    assert.equal(f.audios.length, 2);
    assert.equal(f.audios[0].src, "");
    assert.equal(f.audios[0].paused, true);
    assert.equal(f.audios[1].crossOrigin, null);
    assert.equal(f.nodes[0].connections.length, 0);
    assert.equal(f.state.effectsAvailable, false);
    f.player.destroy();
});

test("autoplay denial stops loading and requests a user gesture instead of retrying", async () => {
    const f = fixture();
    await f.player.load(EPISODE);
    f.audios[0].playImpl = () => Promise.reject(Object.assign(new Error("blocked"), { name: "NotAllowedError" }));
    assert.equal(await f.player.play(), false);
    assert.equal(f.audios.length, 1);
    assert.equal(f.state.playing, false);
    assert.equal(f.state.loading, false);
    assert.match(f.state.error, /Press play/);
    assert.equal(f.timers.size, 0);
    f.player.destroy();
});

test("a failed play promise uses standard streaming as its single fallback", async () => {
    const f = fixture();
    await f.player.load(EPISODE);
    f.audios[0].playImpl = () => Promise.reject(new Error("network failure"));
    assert.equal(await f.player.play(), true);
    assert.equal(f.audios.length, 2);
    assert.equal(f.state.effectsAvailable, false);
    assert.equal(f.state.playing, true);
    f.player.destroy();
});

test("pausing while play is pending cannot restart the same episode", async () => {
    const f = fixture();
    const pending = deferred();
    await f.player.load(EPISODE);
    const audio = f.audios[0];
    audio.playImpl = () => pending.promise.then(() => { audio.paused = false; });
    const playback = f.player.play();
    f.player.pause();
    pending.resolve();
    assert.equal(await playback, false);
    assert.equal(audio.paused, true);
    assert.equal(f.state.playing, false);
    assert.equal(f.state.loading, false);
    assert.equal(f.timers.size, 0);
    // Delayed DOM events are guarded too.
    audio.paused = false;
    audio.emit("playing");
    assert.equal(audio.paused, true);
    f.player.destroy();
});

test("an old play result cannot pause a newer play intent on the same episode", async () => {
    const f = fixture();
    const first = deferred();
    await f.player.load(EPISODE);
    const audio = f.audios[0];
    audio.playImpl = () => first.promise;
    const oldPlayback = f.player.play();
    f.player.pause();
    audio.playImpl = null;
    assert.equal(await f.player.play(), true);
    first.resolve();
    assert.equal(await oldPlayback, false);
    assert.equal(audio.paused, false);
    assert.equal(f.state.playing, true);
    f.player.destroy();
});

test("switching episodes ignores old callbacks, promise results, and errors", async () => {
    const f = fixture();
    const pending = deferred();
    await f.player.load(EPISODE);
    const old = f.audios[0];
    const oldEnded = old.listeners.get("ended");
    const oldError = old.listeners.get("error");
    old.playImpl = () => pending.promise.then(() => { old.paused = false; });
    const oldPlayback = f.player.play();
    await f.player.load({ audio_url: "https://other.example/next.mp3" }, { autoplay: true });
    oldEnded();
    oldError();
    pending.resolve();
    assert.equal(await oldPlayback, false);
    assert.equal(f.audios.length, 2);
    assert.equal(old.paused, true);
    assert.equal(old.listeners.size, 0);
    assert.equal(f.ended, 0);
    assert.equal(f.state.playing, true);
    assert.equal(f.state.error, "");
    f.player.destroy();
});

test("destruction disposes nodes, listeners, timers and pending audio", async () => {
    const f = fixture();
    const pending = deferred();
    await f.player.load(EPISODE, { preset: "vintage" });
    const audio = f.audios[0];
    audio.playImpl = () => pending.promise.then(() => { audio.paused = false; });
    const playback = f.player.play();
    f.player.destroy();
    const snapshotCount = f.snapshots.length;
    pending.resolve();
    assert.equal(await playback, false);
    assert.equal(audio.paused, true);
    assert.equal(audio.src, "");
    assert.equal(audio.listeners.size, 0);
    assert.equal(f.timers.size, 0);
    assert.equal(f.context.state, "closed");
    assert.ok(f.nodes.every((node) => node.connections.length === 0));
    f.player.pause();
    f.player.destroy();
    assert.equal(await f.player.load(EPISODE), false);
    assert.equal(f.snapshots.length, snapshotCount);
    assert.equal(f.calls.filter((call) => call === "close").length, 1);
});

test("clearing an episode releases media and resets state without closing context", async () => {
    const f = fixture();
    await f.player.load(EPISODE, { autoplay: true });
    await f.player.load(null);
    assert.equal(f.audios[0].src, "");
    assert.equal(f.audios[0].listeners.size, 0);
    assert.deepEqual(f.state, {
        playing: false, loading: false, currentTime: 0, duration: 0,
        effectsAvailable: false, notice: "", error: "",
    });
    assert.equal(f.context.state, "running");
    assert.equal(await f.player.load(EPISODE, { autoplay: true }), true);
    f.player.destroy();
});

test("ended fires once and can synchronously load the next queued episode", async () => {
    let ended = 0;
    const f = fixture({ onEnded: () => {
        ended += 1;
        f.player.load({ audio_url: "https://publisher.example/next.mp3" }, { autoplay: true });
    } });
    await f.player.load(EPISODE, { autoplay: true });
    const first = f.audios[0];
    const endedListener = first.listeners.get("ended");
    first.currentTime = 120;
    first.emit("ended");
    endedListener();
    assert.equal(ended, 1);
    assert.equal(first.paused, true);
    assert.equal(f.audios[1].playCalls, 1);
    assert.equal(f.state.playing, true);
    f.player.destroy();
});

test("an ended episode emits once until explicitly replayed", async () => {
    const f = fixture();
    await f.player.load(EPISODE, { autoplay: true });
    const audio = f.audios[0];
    audio.readyState = 1;
    audio.duration = 100;
    audio.currentTime = 100;
    audio.emit("ended");
    audio.emit("ended");
    assert.equal(f.ended, 1);
    assert.equal(f.state.playing, false);
    await f.player.play();
    assert.equal(audio.currentTime, 0);
    audio.emit("ended");
    assert.equal(f.ended, 2);
    f.player.destroy();
});

test("seeking before metadata defers safely and clamps to a finite duration", async () => {
    const f = fixture();
    await f.player.load(EPISODE);
    const audio = f.audios[0];
    f.player.seek(600);
    assert.equal(audio.currentTime, 0);
    assert.equal(f.state.currentTime, 600);
    audio.readyState = 1;
    audio.duration = 120;
    audio.emit("loadedmetadata");
    assert.equal(audio.currentTime, 120);
    assert.equal(f.state.duration, 120);
    f.player.seek(-20);
    assert.equal(audio.currentTime, 0);
    audio.duration = Infinity;
    audio.emit("durationchange");
    assert.equal(f.state.duration, 0);
    f.player.destroy();
});

test("stalled media gets one plain fallback and then a bounded load error", async () => {
    const f = fixture();
    const never = deferred();
    await f.player.load(EPISODE);
    f.audios[0].playImpl = () => never.promise;
    f.player.play();
    assert.equal(f.timers.size, 1);
    f.expire();
    assert.equal(f.audios.length, 2);
    const fallback = f.audios[1];
    fallback.emit("waiting");
    assert.equal(f.timers.size, 1);
    f.expire();
    assert.match(f.state.error, /took too long/);
    assert.equal(f.state.playing, false);
    assert.equal(f.state.loading, false);
    assert.equal(fallback.paused, true);
    assert.equal(f.timers.size, 0);
    f.player.destroy();
});

test("ongoing playback clears a stalled-download deadline", async () => {
    const f = fixture();
    await f.player.load(EPISODE, { autoplay: true });
    const audio = f.audios[0];
    audio.emit("stalled");
    assert.equal(f.timers.size, 1);
    audio.currentTime = 1;
    audio.emit("timeupdate");
    assert.equal(f.timers.size, 0);
    assert.equal(f.state.loading, false);
    f.player.destroy();
});

test("invalid, credentialed, and mixed-content URLs cannot start network playback", async () => {
    for (const audio_url of ["javascript:alert(1)", "data:audio/mpeg;base64,AA==", "/local.mp3", "http://publisher.example/file.mp3", "https://user:password@publisher.example/a.mp3"]) {
        const f = fixture();
        assert.equal(await f.player.load({ audio_url }, { autoplay: true }), false, audio_url);
        assert.equal(f.audios.length, 0);
        assert.ok(f.state.error);
        f.player.destroy();
    }
});

test("HTTP media can be streamed on a non-secure local development page", async () => {
    const f = fixture({ pageProtocol: "http:" });
    assert.equal(await f.player.load({ audio_url: "http://publisher.example/file.mp3" }, { autoplay: true }), true);
    f.player.destroy();
});
