/** Local effects for live publisher audio. This module never fetches or stores media bytes. */

export const DEFAULT_PODCAST_EFFECTS = Object.freeze({ effectMix: 0.75, texture: 0.15, space: 0.15 });

export const PODCAST_PRESETS = Object.freeze([
    { id: "clean", name: "Original", description: "The publisher's sound, exactly as it is.", tag: "Unfiltered", textureLabel: "Texture" },
    { id: "radio", name: "AM Radio", description: "A familiar broadcast sound: focused voices and a little static.", tag: "Broadcast", textureLabel: "Static" },
    { id: "vintage", name: "Golden Era", description: "Warm valve color with the worn edges of an early broadcast.", tag: "1930s–50s", textureLabel: "Crackle" },
    { id: "noir", name: "Noir Lounge", description: "Dark, intimate voices with a soft, late-night room.", tag: "After hours", textureLabel: "Hiss" },
    { id: "newsreel", name: "Newsreel", description: "Brisk, forward speech from a crackling cinema bulletin.", tag: "Archive", textureLabel: "Crackle" },
    { id: "fireside", name: "Fireside", description: "Soft highs and close, gentle warmth for long listening.", tag: "Warm & soft", textureLabel: "Hiss" },
    { id: "gramophone", name: "Gramophone", description: "A narrow, grainy mono voice with old-record character.", tag: "Shellac", textureLabel: "Crackle" },
    { id: "cassette", name: "Cassette", description: "Rounded tape warmth with a subtle wandering pitch.", tag: "Analog tape", textureLabel: "Tape hiss" },
    { id: "telephone", name: "Telephone", description: "A small, clear speech band, like a call down the line.", tag: "On the line", textureLabel: "Line noise" },
    { id: "shortwave", name: "Shortwave", description: "A distant, wavering transmission behind fine radio static.", tag: "Distant signal", textureLabel: "Static" },
    { id: "muffled", name: "Next Room", description: "Low, softened voices drifting in through a closed door.", tag: "Behind the wall", textureLabel: "Room noise" },
].map(Object.freeze));

export function getPodcastPreset(id) {
    return PODCAST_PRESETS.find((preset) => preset.id === id) || PODCAST_PRESETS[0];
}

// Modest gain, linear wet/dry mixing and a room send capped at 20% keep
// correlated dry and treated audio from being doubled at intermediate settings.
const PROFILES = {
    clean:      { high: 20, low: 20000, tone: 1000, color: 0, drive: 1, threshold: -12, ratio: 1, hiss: 0, crackle: 0, room: 0 },
    radio:      { high: 280, low: 3400, tone: 1500, color: 2.5, drive: 1.5, threshold: -22, ratio: 3, hiss: 0.018, crackle: 0.018, room: 0.009, mono: true },
    vintage:    { high: 180, low: 3300, tone: 640, color: 2, drive: 2, threshold: -24, ratio: 2.8, hiss: 0.01, crackle: 0.07, room: 0.023, mono: true },
    noir:       { high: 85, low: 4700, tone: 340, color: 2.7, drive: 1.35, threshold: -19, ratio: 2, hiss: 0.009, crackle: 0, room: 0.075 },
    newsreel:   { high: 430, low: 3900, tone: 1900, color: 3, drive: 2.2, threshold: -27, ratio: 4.5, hiss: 0.012, crackle: 0.06, room: 0.033, mono: true },
    fireside:   { high: 55, low: 6500, tone: 250, color: 1.6, drive: 1.08, threshold: -16, ratio: 1.6, hiss: 0.005, crackle: 0, room: 0.012 },
    gramophone: { high: 540, low: 2400, tone: 1100, color: 2.8, drive: 2.8, threshold: -25, ratio: 3.5, hiss: 0.014, crackle: 0.11, room: 0.018, mono: true },
    cassette:   { high: 65, low: 7200, tone: 420, color: 1.3, drive: 1.55, threshold: -18, ratio: 1.8, hiss: 0.02, crackle: 0, room: 0.018, wow: 0.00075, flutter: 0.00012 },
    telephone:  { high: 520, low: 2600, tone: 1800, color: 1, drive: 1.15, threshold: -22, ratio: 3.2, hiss: 0.009, crackle: 0.005, room: 0.005, mono: true },
    shortwave:  { high: 720, low: 2200, tone: 1400, color: 1.7, drive: 1.85, threshold: -23, ratio: 3.4, hiss: 0.032, crackle: 0.035, room: 0.036, tremolo: 0.07, mono: true },
    muffled:    { high: 35, low: 850, tone: 220, color: 0.8, drive: 1.05, threshold: -14, ratio: 1.5, hiss: 0.004, crackle: 0, room: 0.048 },
};

function unit(value, fallback) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? Math.min(1, Math.max(0, numeric)) : fallback;
}

function randomGenerator(seed) {
    let state = seed;
    return () => {
        state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
        return state / 4294967296;
    };
}

function localBuffer(context, duration, fill) {
    const buffer = context.createBuffer(1, Math.ceil(context.sampleRate * duration), context.sampleRate);
    const data = buffer.getChannelData(0);
    const random = randomGenerator(8317);
    for (let i = 0; i < data.length; i += 1) data[i] = fill(i, data.length, random);
    return buffer;
}

/**
 * Fixed-size graph: changing presets updates parameters without replacing the
 * media element or accumulating effect nodes. Synthetic sources are local and
 * texture sources run only while the player reports actual audible playback.
 */
export function createPodcastEffectsGraph(context, source, destination, options = {}) {
    const nodes = [];
    const oscillators = [];
    let noiseSources = [];
    let destroyed = false;
    let active = false;
    let initializing = true;
    let settings = { preset: "clean", ...DEFAULT_PODCAST_EFFECTS };
    let profile = PROFILES.clean;
    let hissBuffer;
    let crackleBuffer;
    const node = (value) => { nodes.push(value); return value; };
    const gain = (value = 1) => {
        const result = node(context.createGain());
        result.gain.value = value;
        return result;
    };
    const disconnect = (target) => { try { target.disconnect(); } catch { /* Already released. */ } };
    const stop = (target) => { try { target.stop(); } catch { /* Already stopped or not started. */ } disconnect(target); };
    const set = (parameter, value, immediate = false) => {
        const now = context.currentTime;
        if (initializing || immediate) {
            parameter.cancelScheduledValues(now);
            parameter.setValueAtTime(value, now);
        } else {
            if (typeof parameter.cancelAndHoldAtTime === "function") parameter.cancelAndHoldAtTime(now);
            else {
                parameter.cancelScheduledValues(now);
                parameter.setValueAtTime(parameter.value, now);
            }
            parameter.linearRampToValueAtTime(value, now + 0.035);
        }
    };
    const stopNoise = () => {
        for (const noise of noiseSources) stop(noise);
        noiseSources = [];
    };
    const destroy = () => {
        if (destroyed) return;
        destroyed = true;
        stopNoise();
        for (const oscillator of oscillators) stop(oscillator);
        disconnect(source);
        for (const effect of nodes) disconnect(effect);
        hissBuffer = null;
        crackleBuffer = null;
    };

    try {
        const dry = gain(1);
        const input = gain();
        input.channelCountMode = "explicit";
        input.channelInterpretation = "speakers";
        const high = node(context.createBiquadFilter());
        high.type = "highpass";
        high.Q.value = 0.707;
        const low = node(context.createBiquadFilter());
        low.type = "lowpass";
        low.Q.value = 0.707;
        const tone = node(context.createBiquadFilter());
        tone.type = "peaking";
        tone.Q.value = 0.8;
        const compressor = node(context.createDynamicsCompressor());
        compressor.knee.value = 16;
        compressor.attack.value = 0.008;
        compressor.release.value = 0.2;
        const drive = gain();
        const saturation = node(context.createWaveShaper());
        const curve = new Float32Array(2049);
        for (let i = 0; i < curve.length; i += 1) {
            const x = 2 * i / (curve.length - 1) - 1;
            curve[i] = Math.tanh(x * 1.5) / 1.5;
        }
        saturation.curve = curve;
        saturation.oversample = "2x";
        const compensation = gain();
        const tapeDelay = node(context.createDelay(0.03));
        const tremolo = gain();
        const wet = gain(0);
        const roomDelay = node(context.createDelay(0.2));
        const roomTone = node(context.createBiquadFilter());
        roomTone.type = "lowpass";
        roomTone.frequency.value = 3800;
        const room = node(context.createConvolver());
        room.buffer = localBuffer(context, 0.38, (i, length, random) => {
            // Tiny room reflections, with an attack that avoids a second dry hit.
            const attack = Math.min(1, i / (context.sampleRate * 0.007));
            return (random() * 2 - 1) * attack * Math.pow(1 - i / length, 3.3);
        });
        const roomGain = gain(0);
        const auxGate = gain(0);
        const hissFilter = node(context.createBiquadFilter());
        hissFilter.type = "highpass";
        hissFilter.frequency.value = 900;
        const crackleFilter = node(context.createBiquadFilter());
        crackleFilter.type = "lowpass";
        crackleFilter.frequency.value = 4300;
        const hissGain = gain(0);
        const crackleGain = gain(0);

        const connectChain = (...chain) => {
            for (let i = 0; i < chain.length - 1; i += 1) chain[i].connect(chain[i + 1]);
        };
        connectChain(source, dry, destination);
        connectChain(source, input, high, low, tone, compressor, drive, saturation, compensation, tapeDelay, tremolo, wet, destination);
        connectChain(tremolo, roomDelay, roomTone, room, roomGain, auxGate, destination);
        connectChain(hissFilter, hissGain, auxGate);
        connectChain(crackleFilter, crackleGain, auxGate);

        const lfo = (frequency, parameter) => {
            const oscillator = node(context.createOscillator());
            oscillators.push(oscillator);
            oscillator.frequency.value = frequency;
            const depth = gain(0);
            connectChain(oscillator, depth, parameter);
            oscillator.start();
            return depth.gain;
        };
        const wow = lfo(0.63, tapeDelay.delayTime);
        const flutter = lfo(5.7, tapeDelay.delayTime);
        const fading = lfo(4.8, tremolo.gain);

        const startNoise = () => {
            if (noiseSources.length) return;
            hissBuffer ||= localBuffer(context, 2.7, (_i, _length, random) => (random() * 2 - 1) * 0.55);
            let crackleTail = 0;
            crackleBuffer ||= localBuffer(context, 3.1, (_i, _length, random) => {
                if (random() < 14 / context.sampleRate) crackleTail = (random() * 2 - 1) * 0.75;
                crackleTail *= 0.86;
                return crackleTail;
            });
            for (const [buffer, target] of [[hissBuffer, hissFilter], [crackleBuffer, crackleFilter]]) {
                const noise = context.createBufferSource();
                noiseSources.push(noise);
                noise.buffer = buffer;
                noise.loop = true;
                noise.connect(target);
                noise.start();
            }
        };
        const syncAuxiliary = () => {
            const treated = settings.preset !== "clean" && settings.effectMix > 0;
            const audible = active && treated;
            // Close the gate immediately on pause, buffering, mute and end so
            // synthetic noise or an old room tail cannot continue on its own.
            set(auxGate.gain, audible ? 1 : 0, !audible);
            if (audible && settings.texture > 0 && (profile.hiss || profile.crackle)) startNoise();
            else stopNoise();
        };
        const update = (changes = {}) => {
            if (destroyed) return;
            settings = {
                preset: getPodcastPreset(changes.preset ?? settings.preset).id,
                effectMix: unit(changes.effectMix ?? settings.effectMix, DEFAULT_PODCAST_EFFECTS.effectMix),
                texture: unit(changes.texture ?? settings.texture, DEFAULT_PODCAST_EFFECTS.texture),
                space: unit(changes.space ?? settings.space, DEFAULT_PODCAST_EFFECTS.space),
            };
            profile = PROFILES[settings.preset];
            const mix = settings.preset === "clean" ? 0 : settings.effectMix;
            const roomAmount = settings.space * 0.2;
            set(dry.gain, 1 - mix);
            set(wet.gain, mix * (1 - roomAmount));
            set(roomGain.gain, mix * roomAmount);
            set(hissGain.gain, mix * settings.texture * profile.hiss);
            set(crackleGain.gain, mix * settings.texture * profile.crackle);
            input.channelCount = profile.mono ? 1 : 2;
            set(high.frequency, profile.high);
            set(low.frequency, Math.min(profile.low, context.sampleRate * 0.45));
            set(tone.frequency, profile.tone);
            set(tone.gain, profile.color);
            set(compressor.threshold, profile.threshold);
            set(compressor.ratio, profile.ratio);
            set(drive.gain, profile.drive);
            // Preset gain is conservative; EQ and grit should not cause a jump.
            set(compensation.gain, Math.pow(10, -profile.color / 20) / profile.drive);
            set(tapeDelay.delayTime, profile.wow ? 0.006 : 0);
            set(wow, profile.wow || 0);
            set(flutter, profile.flutter || 0);
            set(tremolo.gain, 1 - (profile.tremolo || 0));
            set(fading, profile.tremolo || 0);
            set(roomDelay.delayTime, profile.room);
            syncAuxiliary();
        };
        update(options);
        initializing = false;
        return {
            update,
            setPlaybackActive(value) {
                if (destroyed) return;
                const next = Boolean(value);
                if (active === next) return;
                active = next;
                syncAuxiliary();
            },
            destroy,
        };
    } catch (error) {
        destroy();
        throw error;
    }
}
