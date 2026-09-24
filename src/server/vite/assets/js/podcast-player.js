/**
 * One streamed episode at a time. The queue belongs to the library UI.
 * Media goes straight from the publisher to an HTMLAudioElement; Web Audio
 * only filters that live stream. Nothing is fetched into an AudioBuffer.
 * Keep this instance in a closure, outside Alpine's reactive state.
 */

import { createPodcastEffectsGraph, DEFAULT_PODCAST_EFFECTS, getPodcastPreset } from "./podcast-effects.js";
const FILTER_NOTICE = "Filters are unavailable for this episode on this host or browser. Standard playback is used.";
const BROWSER_NOTICE = "Audio filters are unavailable in this browser. Standard playback is used.";

function finite(value, fallback = 0) {
    return Number.isFinite(Number(value)) ? Number(value) : fallback;
}

function volumeValue(value) {
    return Math.min(1, Math.max(0, finite(value)));
}

function neutralState() {
    return {
        playing: false,
        loading: false,
        currentTime: 0,
        duration: 0,
        effectsAvailable: false,
        notice: "",
        error: "",
    };
}

function mediaUrl(value, pageProtocol) {
    let url;
    try {
        url = new URL(value);
    } catch {
        throw new Error("This episode does not have a valid audio address.");
    }
    if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) {
        throw new Error("This episode needs a public HTTP or HTTPS audio address.");
    }
    if (pageProtocol === "https:" && url.protocol !== "https:") {
        throw new Error("This episode uses an insecure HTTP address. Choose an episode with an HTTPS audio address.");
    }
    return url.href;
}

export class PodcastPlayer {
    constructor({
        onChange = () => {},
        onEnded = () => {},
        audioFactory = () => new globalThis.Audio(),
        audioContextFactory = () => {
            const Context = globalThis.AudioContext || globalThis.webkitAudioContext;
            return Context ? new Context() : null;
        },
        pageProtocol = globalThis.location?.protocol || "https:",
        stallTimeoutMs = 35000,
        scheduleTimeout = globalThis.setTimeout.bind(globalThis),
        cancelTimeout = globalThis.clearTimeout.bind(globalThis),
    } = {}) {
        this._onChange = onChange;
        this._onEnded = onEnded;
        this._audioFactory = audioFactory;
        this._contextFactory = audioContextFactory;
        this._pageProtocol = pageProtocol;
        this._stallTimeoutMs = stallTimeoutMs;
        this._scheduleTimeout = scheduleTimeout;
        this._cancelTimeout = cancelTimeout;
        this._state = neutralState();
        this._media = null;
        this._context = null;
        this._destroyed = false;
        this._wantsPlay = false;
        this._playRevision = 0;
        this._volume = 0.75;
        this._preset = "clean";
        this._effects = { ...DEFAULT_PODCAST_EFFECTS };
        this._url = "";
    }

    load(episode, { volume = 0.75, preset = "clean", autoplay = false,
        effectMix = DEFAULT_PODCAST_EFFECTS.effectMix, texture = DEFAULT_PODCAST_EFFECTS.texture,
        space = DEFAULT_PODCAST_EFFECTS.space } = {}) {
        if (this._destroyed) return Promise.resolve(false);
        this._wantsPlay = false;
        this._playRevision += 1;
        this._releaseMedia();
        this._state = neutralState();
        this._url = "";
        this._volume = volumeValue(volume);
        this._preset = getPodcastPreset(preset).id;
        this._effects = { effectMix: volumeValue(effectMix), texture: volumeValue(texture), space: volumeValue(space) };
        if (!episode) {
            this._emit();
            return Promise.resolve(true);
        }
        try {
            this._url = mediaUrl(episode.audio_url, this._pageProtocol);
            if (!this._context || this._context.state === "closed") {
                try { this._context = this._contextFactory(); } catch { this._context = null; }
            }
            this._replaceMedia(Boolean(this._context));
        } catch (error) {
            this._releaseMedia();
            this._state.error = error.message || "This episode could not be opened.";
            this._emit();
            return Promise.resolve(false);
        }
        this._emit();
        return autoplay ? this.play() : Promise.resolve(true);
    }

    play() {
        if (this._destroyed || !this._media) return Promise.resolve(false);
        let record = this._media;
        if (record.failed) {
            try {
                this._replaceMedia(record.filtered, this._state.currentTime);
                record = this._media;
            } catch {
                this._fail(this._media, "This episode could not be opened. Try another episode.");
                return Promise.resolve(false);
            }
        }
        if (record.ended) {
            record.ended = false;
            this.seek(0);
        }
        this._wantsPlay = true;
        const revision = ++this._playRevision;
        this._state.error = "";
        this._state.loading = true;
        this._armStallTimer(record);
        this._emit();

        // Both calls must happen in the original user gesture, before awaiting
        // either promise. This matters for audio unlocking on mobile browsers.
        let resume;
        let playback;
        try {
            resume = record.filtered && this._context.state !== "running"
                ? Promise.resolve(this._context.resume())
                : Promise.resolve();
        } catch (error) {
            resume = Promise.reject(error);
        }
        try { playback = Promise.resolve(record.audio.play()); } catch (error) { playback = Promise.reject(error); }

        return Promise.all([resume, playback]).then(() => {
            if (!this._isCurrent(record)) {
                record.audio.pause();
                return record.fallbackPromise || false;
            }
            if (revision !== this._playRevision || !this._wantsPlay) {
                if (!this._wantsPlay) record.audio.pause();
                return false;
            }
            this._state.playing = !record.audio.paused;
            this._state.loading = false;
            this._clearStallTimer(record);
            this._emit();
            return this._state.playing;
        }).catch((error) => {
            if (!this._isCurrent(record)) return record.fallbackPromise || false;
            if (revision !== this._playRevision || !this._wantsPlay) return false;
            if (error?.name === "NotAllowedError") {
                this._fail(record, "Your browser needs a play-button press to start this episode. Press play to try again.");
                return false;
            }
            return this._mediaFailure(record);
        });
    }

    pause() {
        if (this._destroyed) return;
        this._wantsPlay = false;
        this._playRevision += 1;
        if (this._media) {
            this._clearStallTimer(this._media);
            this._media.audio.pause();
        }
        this._state.playing = false;
        this._state.loading = false;
        this._emit();
    }

    seek(seconds) {
        if (this._destroyed || !this._media) return;
        const upper = this._state.duration > 0 ? this._state.duration : Infinity;
        const position = Math.min(upper, Math.max(0, finite(seconds)));
        const record = this._media;
        record.pendingSeek = position;
        if (record.audio.readyState >= 1) this._applyPendingSeek(record);
        record.ended = false;
        this._state.currentTime = position;
        this._emit();
    }

    setVolume(volume) {
        if (this._destroyed) return;
        this._volume = volumeValue(volume);
        if (!this._media) return;
        if (this._media.gain) {
            const parameter = this._media.gain.gain;
            const now = this._context.currentTime;
            if (typeof parameter.cancelAndHoldAtTime === "function") parameter.cancelAndHoldAtTime(now);
            else {
                parameter.cancelScheduledValues(now);
                parameter.setValueAtTime(parameter.value, now);
            }
            parameter.linearRampToValueAtTime(this._volume, now + 0.02);
        }
        else this._media.audio.volume = this._volume;
        this._syncEffectsPlayback();
    }

    setPreset(preset) {
        if (this._destroyed) return;
        this._preset = getPodcastPreset(preset).id;
        this._updateEffects();
        this._emit();
    }

    setEffectMix(value) { this._setEffectControl("effectMix", value); }

    setTexture(value) { this._setEffectControl("texture", value); }

    setSpace(value) { this._setEffectControl("space", value); }

    _setEffectControl(control, value) {
        if (this._destroyed) return;
        this._effects[control] = volumeValue(value);
        this._updateEffects();
    }

    _updateEffects() {
        if (!this._media?.effects) return;
        try { this._media.effects.update({ preset: this._preset, ...this._effects }); }
        catch { this._mediaFailure(this._media); }
    }

    _syncEffectsPlayback() {
        const record = this._media;
        if (!record?.effects) return;
        try {
            record.effects.setPlaybackActive(this._wantsPlay && this._state.playing && !this._state.loading
                && !record.audio.paused && !record.audio.muted && record.audio.volume > 0
                && !record.ended && !record.failed && this._volume > 0);
        } catch { this._mediaFailure(record); }
    }

    destroy() {
        if (this._destroyed) return;
        this._destroyed = true;
        this._wantsPlay = false;
        this._playRevision += 1;
        this._releaseMedia();
        if (this._context) {
            try { Promise.resolve(this._context.close()).catch(() => {}); } catch { /* Already closed. */ }
            this._context = null;
        }
        this._onChange = () => {};
        this._onEnded = () => {};
    }

    _isCurrent(record) {
        return !this._destroyed && this._media === record;
    }

    _emit() {
        if (!this._destroyed) {
            this._syncEffectsPlayback();
            this._onChange({ ...this._state });
        }
    }

    _replaceMedia(filtered, position = 0) {
        this._releaseMedia();
        const audio = this._audioFactory();
        const record = {
            audio, filtered, listeners: [], effects: null, source: null, gain: null,
            timer: null, pendingSeek: position > 0 ? position : null,
            ended: false, failed: false, fallbackPromise: null,
        };
        this._media = record;
        audio.preload = "none";
        audio.playsInline = true;
        if (filtered) audio.crossOrigin = "anonymous";
        this._state.effectsAvailable = filtered;
        this._state.playing = false;
        if (filtered) {
            try {
                record.source = this._context.createMediaElementSource(audio);
                record.gain = this._context.createGain();
                record.gain.gain.value = this._volume;
                record.gain.connect(this._context.destination);
                audio.volume = 1;
                record.effects = createPodcastEffectsGraph(this._context, record.source, record.gain,
                    { preset: this._preset, ...this._effects });
            } catch {
                this._state.notice = BROWSER_NOTICE;
                this._replaceMedia(false, position);
                return;
            }
        } else {
            audio.volume = this._volume;
            if (!this._state.notice) this._state.notice = BROWSER_NOTICE;
        }

        const listen = (event, handler) => {
            const listener = () => { if (this._isCurrent(record)) handler(); };
            audio.addEventListener(event, listener);
            record.listeners.push([event, listener]);
        };
        const updateTime = () => {
            this._state.duration = Math.max(0, finite(audio.duration));
            this._state.currentTime = record.pendingSeek ?? Math.max(0, finite(audio.currentTime));
            this._emit();
        };
        listen("loadedmetadata", () => { this._applyPendingSeek(record); updateTime(); });
        listen("durationchange", updateTime);
        listen("timeupdate", () => {
            if (this._wantsPlay && !audio.paused && audio.currentTime > this._state.currentTime) {
                this._state.loading = false;
                this._clearStallTimer(record);
            }
            updateTime();
        });
        listen("playing", () => {
            // A delayed play event must never undo a pause or a failed request.
            if (!this._wantsPlay || record.failed || record.ended) { audio.pause(); return; }
            this._state.playing = true;
            this._state.loading = false;
            this._clearStallTimer(record);
            this._emit();
        });
        listen("pause", () => {
            this._state.playing = false;
            if (!this._wantsPlay) this._state.loading = false;
            this._emit();
        });
        listen("volumechange", () => this._syncEffectsPlayback());
        for (const event of ["waiting", "stalled", "seeking"]) {
            listen(event, () => {
                if (!this._wantsPlay) return;
                this._state.loading = true;
                this._armStallTimer(record);
                this._emit();
            });
        }
        listen("seeked", () => {
            if (!audio.paused && audio.readyState >= 3) {
                this._state.loading = false;
                this._clearStallTimer(record);
            }
            updateTime();
        });
        listen("error", () => { this._mediaFailure(record); });
        listen("ended", () => {
            if (record.ended || record.failed) return;
            record.ended = true;
            this._wantsPlay = false;
            this._playRevision += 1;
            this._clearStallTimer(record);
            this._state.playing = false;
            this._state.loading = false;
            this._state.currentTime = Math.max(0, finite(audio.currentTime));
            this._emit();
            if (this._isCurrent(record)) this._onEnded();
        });
        // Setting src does not force a download: preload stays "none" and
        // load() is deliberately reserved for disposing old elements.
        audio.src = this._url;
    }

    _applyPendingSeek(record) {
        if (record.pendingSeek == null) return;
        const duration = finite(record.audio.duration);
        const position = Math.min(record.pendingSeek, duration > 0 ? duration : Infinity);
        try {
            record.audio.currentTime = position;
            record.pendingSeek = null;
        } catch { /* Some hosts do not permit seeking until more data arrives. */ }
    }

    _mediaFailure(record, timedOut = false) {
        if (!this._isCurrent(record) || record.failed) return Promise.resolve(false);
        if (record.filtered) {
            const wanted = this._wantsPlay;
            const position = record.pendingSeek ?? Math.max(0, finite(record.audio.currentTime, this._state.currentTime));
            this._state.notice = FILTER_NOTICE;
            this._playRevision += 1;
            try {
                // A MediaElementSource cannot be detached from its element.
                // A fresh non-CORS element is essential for ordinary playback.
                this._replaceMedia(false, position);
            } catch {
                this._fail(this._media, "This episode could not be opened. Try another episode.");
                return Promise.resolve(false);
            }
            this._state.loading = wanted;
            this._emit();
            record.fallbackPromise = wanted ? this.play() : Promise.resolve(false);
            return record.fallbackPromise;
        }
        this._fail(record, timedOut
            ? "This episode took too long to load. Check your connection and try again, or choose another episode."
            : "This episode could not be played. Its audio may be unavailable or unsupported by your browser. Try another episode.");
        return Promise.resolve(false);
    }

    _fail(record, message) {
        if (record && !this._isCurrent(record)) return;
        this._wantsPlay = false;
        this._playRevision += 1;
        this._state.playing = false;
        this._state.loading = false;
        this._state.error = message;
        if (record) {
            record.failed = true;
            this._clearStallTimer(record);
            record.audio.pause();
        }
        this._emit();
    }

    _armStallTimer(record) {
        if (record.timer != null) return;
        record.timer = this._scheduleTimeout(() => {
            record.timer = null;
            if (this._isCurrent(record) && this._wantsPlay) this._mediaFailure(record, true);
        }, this._stallTimeoutMs);
    }

    _clearStallTimer(record) {
        if (record.timer != null) this._cancelTimeout(record.timer);
        record.timer = null;
    }

    _releaseMedia() {
        const record = this._media;
        this._media = null;
        if (!record) return;
        this._clearStallTimer(record);
        for (const [event, listener] of record.listeners) record.audio.removeEventListener(event, listener);
        record.audio.pause();
        record.effects?.destroy();
        for (const node of [record.source, record.gain]) {
            try { node?.disconnect(); } catch { /* Already disconnected. */ }
        }
        record.audio.removeAttribute("src");
        record.audio.load();
    }
}
