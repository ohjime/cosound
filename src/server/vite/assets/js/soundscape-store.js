import { DEFAULT_LOUDNESS_TARGET, SoundscapeMixer } from "./soundscape-mixer.js";

/**
 * How many layers one mix may hold.
 *
 * The studio's `+` goes inert at this count and addLayer refuses past it, so a
 * ninth voice never reaches the graph however it was asked for.
 */
export const MAX_LAYERS = 8;
const LOADING_PROGRESS_SETTLE_MS = 350;

/** Let the radial progress paint 100% before its loading view is dismissed. */
function settleLoadingProgress() {
    if (typeof requestAnimationFrame !== "function") return Promise.resolve();
    return new Promise((resolve) => {
        requestAnimationFrame(() => {
            setTimeout(resolve, LOADING_PROGRESS_SETTLE_MS);
        });
    });
}

/**
 * Stand-in cover art, so a layer with no artwork has something to show instead
 * of a broken <img>. A data: URI keeps it inline — there is no request to make
 * and nothing to revoke.
 */
function placeholderArtwork(title) {
    const initial = (String(title ?? "").trim()[0] || "?").toUpperCase()
        .replace(/[<>&"']/g, "?");
    const svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 400'>"
        + "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
        + "<stop offset='0' stop-color='#1f3f23'/>"
        + "<stop offset='1' stop-color='#0b140d'/></linearGradient></defs>"
        + "<rect width='400' height='400' fill='url(#g)'/>"
        + "<text x='200' y='200' text-anchor='middle' dominant-baseline='central' "
        + "font-family='Georgia,serif' font-size='190' fill='#ffffff' "
        + `fill-opacity='0.2'>${initial}</text></svg>`;
    return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

/**
 * Warm an artwork URL before the reactive layer is replaced. The picker has
 * usually loaded the thumbnail already, but this also covers searched sounds
 * and an evicted browser cache. A broken image must not strand the swapping
 * screen; c-core-image handles that case with its normal fallback behaviour.
 */
function preloadArtwork(url) {
    if (!url || typeof Image === "undefined") return Promise.resolve();
    return new Promise((resolve) => {
        const image = new Image();
        let settled = false;
        const finish = () => {
            if (settled) return;
            settled = true;
            resolve();
        };
        image.onload = finish;
        image.onerror = finish;
        image.src = url;
        if (image.complete) finish();
    });
}

/** Give Alpine one painted frame to bind the newly cached artwork. */
function afterNextPaint() {
    if (typeof requestAnimationFrame !== "function") {
        return new Promise((resolve) => queueMicrotask(resolve));
    }
    return new Promise((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(resolve));
    });
}

function normalizeUiLayer(layer) {
    return {
        ...layer,
        // A blank layer arrives with no art — including the one the server
        // seeds the studio with, which cannot call this helper itself.
        artwork_url: layer.artwork_url || placeholderArtwork(layer.sound_title),
        gain: layer.sound_gain != null
            ? Number(layer.sound_gain) * 100
            : Number(layer.gain ?? 50),
        saved: layer.saved ?? false,
        isolated: false,
        mute: Boolean(layer.mute),
        // Playback shape, surfaced by the studio's settings pane. Both feed
        // layerConfig, so changing either re-prepares the voice.
        playback_rate: Number(layer.playback_rate ?? 1),
        stretch: Number(layer.stretch ?? 1.75),
        // How long each repeat of the layer fades into the next, in seconds.
        // Zero is the hard join; the ceiling below is written by _syncAnalysis,
        // because only the engine knows how long a pass turned out to be.
        loop_crossfade: Math.max(0, Number(layer.loop_crossfade ?? 0) || 0),
        loop_crossfade_max: Number(layer.loop_crossfade_max ?? 0),
        // The crop, in seconds from the head of the file. A null end means "to
        // the end", which is what an uncropped layer carries and what a layer
        // falls back to whenever it is given a different file.
        trim_start: Number(layer.trim_start ?? 0),
        trim_end: layer.trim_end == null ? null : Number(layer.trim_end),
        // The loudness the layer is matched to, in LUFS; null is off.
        loudness_target: layer.loudness_target == null
            ? null
            : Number(layer.loudness_target),
        // Written by _syncAnalysis once the engine has decoded the file — the
        // settings pane cannot size a crop slider or report a reading until it
        // knows how long the track is and how loud it measured.
        duration: Number(layer.duration ?? 0),
        loudness: layer.loudness ?? null,
        loudness_gain_db: Number(layer.loudness_gain_db ?? 0),
        // A layer the artist dropped in from their own machine. Its audio and
        // artwork are blob: URLs that exist only in this tab, so it has no
        // Sound row behind it and cannot take part in a saved mix.
        isLocal: Boolean(layer.is_local ?? layer.isLocal),
        // A blank layer the artist has not given audio to yet. It holds a
        // silent voice so the index mapping between store.layers and the
        // engine's voices stays one-to-one.
        isDraft: Boolean(layer.is_draft ?? layer.isDraft),
        // A blank layer the artist chose to make a new sound out of, rather
        // than fill from the library. It is still a draft — there is no audio
        // behind it yet — but its words are the artist's to write, so the card
        // shows them as fields. Anything that replaces the layer drops it.
        isNew: Boolean(layer.is_new ?? layer.isNew),
        tag_list: Array.isArray(layer.tag_list) ? [...layer.tag_list] : [],
    };
}

/**
 * Revoke the blob: URLs an outgoing layer owned, except any the replacement
 * still points at. Called wherever a layer leaves this.layers.
 */
function revokeUnusedUrls(outgoing, next = null) {
    if (!outgoing?.isLocal) return;
    const keep = new Set([next?.sound_file, next?.artwork_url]);
    for (const url of [outgoing.sound_file, outgoing.artwork_url]) {
        if (typeof url === "string" && url.startsWith("blob:") && !keep.has(url)) {
            URL.revokeObjectURL(url);
        }
    }
}

function revokeLocalUrls(layer) {
    revokeUnusedUrls(layer, null);
}

function layerConfig(layer) {
    return {
        id: layer.sound_id,
        urlA: layer.sound_file_a ?? layer.sound_file,
        urlB: layer.sound_file_b ?? layer.sound_file,
        level: Number(layer.gain) / 100,
        muted: Boolean(layer.mute),
        solo: Boolean(layer.isolated),
        playbackRate: Number(layer.playback_rate ?? 1),
        stretch: Number(layer.stretch ?? 1.75),
        loopCrossfade: Number(layer.loop_crossfade ?? 0),
        trimStart: Number(layer.trim_start ?? 0),
        trimEnd: layer.trim_end == null ? null : Number(layer.trim_end),
        loudnessTarget: layer.loudness_target == null
            ? null
            : Number(layer.loudness_target),
    };
}

function indexOfLayer(store, layer) {
    return store.layers.indexOf(layer);
}

function emit(name, detail = {}) {
    document.dispatchEvent(new CustomEvent(`cosound:audio:${name}`, { detail }));
}

/**
 * @param {object[]} rawLayers  the mix this store opens on
 * @param {object}   [options]
 * @param {boolean}  [options.allowAdd]   may this mix grow at all
 * @param {string}   [options.artistName] credited on a new sound (createSound)
 * @param {boolean}  [options.allowCreate] may a blank layer become a new sound
 * @param {Function} [options.settleProgress] waits for the loading-ring finish
 */
export function createSoundLayersStore(rawLayers, {
    allowAdd = true,
    allowCreate = false,
    artistName = "",
    settleProgress = settleLoadingProgress,
} = {}) {
    // The files behind each new sound, by layer id, kept for createNewSounds.
    // Out here rather than on the layer: Alpine would wrap a File on a reactive
    // layer in a Proxy, and FormData refuses anything that is not a real Blob.
    const newSoundFiles = new Map();
    return {
        layers: rawLayers.map(normalizeUiLayer),
        maxLayers: MAX_LAYERS,
        // Whether this mix takes new layers at all, decided once by whoever
        // mounted the store (c-core-sound-player). It sits here rather than on a
        // card or a deck because there is exactly one mix per page and several
        // components render it: the `+` on the layer indicator reads this, and
        // so does every path that appends, so switching it off closes all of
        // them at once instead of only hiding the obvious button.
        allowAdd,
        // Who a new sound is credited to when the artist presses Create. A
        // blank layer is not stamped with it: no one owns the void.
        artistName,
        // Whether a blank layer offers "Create" beside "Library". Only the
        // home page's LIBRARY tab switches it on, and only for a signed-in
        // artist; the empty card reads it, so one card serves both cases.
        allowCreate,
        // Where the settings pane's loudness toggle switches a layer on to, so
        // the panel does not have to hard-code a number the engine owns.
        loudnessDefault: DEFAULT_LOUDNESS_TARGET,
        currentIndex: 0,
        tracksLoading: true,
        loadedCount: 0,
        loadingTotal: rawLayers.length,
        swappingLayer: false,
        swapLoading: false,
        started: false,
        paused: false,
        loadError: "",
        // The name this mix is currently known by: the title of the saved
        // Cosound it was loaded from, or the one it was last saved under. It
        // survives edits on purpose — tweak a loaded Cosound and the save
        // dialog still opens on its name, so keeping that name overwrites it
        // and typing a new one keeps both. Empty means this mix has never been
        // named, and the dialog opens blank.
        loadedTitle: "",
        _engine: null,

        get currentLayer() {
            return this.layers[this.currentIndex];
        },
        get isFirst() {
            return this.currentIndex === 0;
        },
        get isLast() {
            return this.currentIndex === this.layers.length - 1;
        },
        get isEmpty() {
            return this.layers.length === 0;
        },
        get isFull() {
            return this.layers.length >= this.maxLayers;
        },
        // The one thing the `+` button asks. It goes at the cap as well as when
        // adding is switched off, so a full mix simply stops offering.
        get canAddLayer() {
            return this.allowAdd && !this.isFull;
        },
        // A layer the artist has made room for but not yet given a sound to.
        // Every per-layer control keys off this: there is nothing to fade,
        // mute, solo or keep until the layer has audio in it.
        get currentIsDraft() {
            return Boolean(this.currentLayer?.isDraft);
        },
        // The layers a save is made of. A blank layer is a slot the artist has
        // not filled yet, not a part of the mix, so every save decision looks
        // past it: it neither blocks the button nor goes into the POST. That
        // makes a mix of nothing but blank layers an empty one.
        get savableLayers() {
            return this.layers.filter((layer) => !layer.isDraft);
        },
        // A new sound is local too until it is saved, but unlike a dropped
        // track it has somewhere to go: the save dialog creates its Sound row
        // (createNewSounds) before the mix is saved. So it does not count here.
        get hasLocalLayers() {
            return this.savableLayers.some((layer) => layer.isLocal && !layer.isNew);
        },
        // What a new sound still lacks before it can become a Sound, or "".
        // Every new sound is checked, including one still waiting for its
        // audio: that one is a draft and so not in savableLayers, and saving
        // past it would drop the artist's words without a word.
        get newSoundBlockedReason() {
            for (const layer of this.layers) {
                if (!layer.isNew) continue;
                if (layer.isDraft) return "Your new sound needs a sound file.";
                if (!layer.sound_title?.trim()) return "Your new sound needs a title.";
                // The name, not the file map: this getter has to re-run when
                // artwork is picked, and only the layer is reactive.
                if (!layer.artwork_file_name) return "Your new sound needs artwork.";
            }
            return "";
        },
        get hasNewSounds() {
            return this.savableLayers.some((layer) => layer.isNew);
        },
        // Saving a mix posts sound_ids the server resolves to Sound rows, so a
        // mix holding a browser-local track has nothing to point at. The studio
        // uses this to explain why the save button is off rather than failing
        // the POST.
        get canSave() {
            return this.savableLayers.length > 0
                && !this.hasLocalLayers
                && !this.newSoundBlockedReason;
        },
        get saveBlockedReason() {
            if (this.savableLayers.length === 0 && !this.newSoundBlockedReason) {
                return "Can't save empty Cosound.";
            }
            if (this.hasLocalLayers) {
                return "Mixes with your own tracks stay on this device.";
            }
            return this.newSoundBlockedReason;
        },
        // What the save button posts: each layer's id and level. A new sound
        // has no id the server knows yet, so it is marked, and the save dialog
        // creates it before the mix is saved.
        get saveLayers() {
            return this.savableLayers.map((layer) => ({
                sound_id: layer.sound_id,
                sound_gain: this.isSilenced(layer) ? 0 : layer.gain / 100,
                ...(layer.isNew ? { is_new: true } : {}),
            }));
        },

        anyIsolated() {
            return this.layers.some((layer) => layer.isolated);
        },
        isSilenced(layer) {
            return layer.mute || (this.anyIsolated() && !layer.isolated);
        },
        /**
         * How grey a layer's artwork reads on the card: fully grey once it is
         * silenced, easing back to colour as its fader comes up.
         *
         * A blank layer is exempt. It has no artwork — the card draws its own
         * face for it — and greying that by a fader nobody can move yet would
         * only make an empty slot look broken.
         */
        grayscaleFor(layer) {
            if (!layer || layer.isDraft) return 0;
            if (this.isSilenced(layer)) return 100;
            return Math.max(0, Math.min(100, 100 - (layer.gain || 0)));
        },
        clearIsolation() {
            this.layers.forEach((layer) => {
                layer.isolated = false;
            });
            this._syncAudibility();
        },
        setGain(layer, value) {
            const index = indexOfLayer(this, layer);
            if (index < 0) return;
            layer.gain = Number(value);
            layer.mute = false;
            if (!layer.isolated && this.anyIsolated()) {
                this.layers.forEach((candidate) => {
                    candidate.isolated = false;
                });
            }
            this._syncAudibility();
        },
        toggleMute(layer) {
            const wasMuted = layer.mute;
            layer.mute = !layer.mute;
            if (wasMuted && !layer.isolated && this.anyIsolated()) {
                this.layers.forEach((candidate) => {
                    candidate.isolated = false;
                });
            }
            this._syncAudibility();
        },
        toggleIsolate(layer) {
            if (layer.isolated) {
                layer.isolated = false;
                this._syncAudibility();
                return;
            }
            this.layers.forEach((candidate) => {
                if (candidate !== layer && candidate.isolated) {
                    candidate.isolated = false;
                    candidate.mute = true;
                }
            });
            layer.mute = false;
            layer.isolated = true;
            this._syncAudibility();
        },
        _syncAudibility() {
            if (!this._engine) return;
            this.layers.forEach((layer, index) => {
                this._engine.setLayerGain(index, Number(layer.gain) / 100);
                this._engine.setLayerMute(index, Boolean(layer.mute));
                this._engine.setLayerSolo(index, Boolean(layer.isolated));
            });
        },

        /**
         * Copy back what only the engine can know about a layer: the decoded
         * file's length, where its crop actually landed, its loop crossfade and
         * its loudness.
         *
         * The crop and the crossfade are written back rather than merely read,
         * because the engine corrects them — a start dragged past the end, a
         * crop left over from a longer file, a fade longer than half the pass
         * it has to fit in. Writing the corrected numbers onto the layer is what
         * makes the slider snap to what is really being played instead of
         * sitting at a value that no longer means anything.
         */
        _syncAnalysis(index) {
            const layer = this.layers[index];
            const analysis = this._engine?.layerAnalysis(index);
            if (!layer || !analysis) return;
            layer.duration = analysis.duration;
            layer.trim_start = analysis.trimStart;
            layer.trim_end = analysis.trimEnd;
            layer.loop_crossfade = analysis.loopCrossfade;
            layer.loop_crossfade_max = analysis.loopCrossfadeMax;
            layer.loudness = analysis.loudness;
            layer.loudness_gain_db = analysis.loudnessGainDb;
        },
        _syncAllAnalysis() {
            this.layers.forEach((_, index) => this._syncAnalysis(index));
        },

        /**
         * Match a layer to a loudness in LUFS, or pass null to leave it alone.
         *
         * No rebuild: the engine applies the make-up gain on the voice's own
         * gain node, so dragging the target is as live as dragging the fader.
         * The first switch-on pays for one measurement of the cropped region;
         * every later move of the slider reads it from the engine's cache.
         */
        setLoudness(index, target) {
            const layer = this.layers[index];
            if (!layer || !this._engine) return;
            layer.loudness_target = target == null ? null : Number(target);
            this._engine.setLayerLoudness(index, layer.loudness_target);
            this._syncAnalysis(index);
            emit("loudness", { index, layer });
        },

        async initialize() {
            // Tear down the audio graph only. destroy() would also revoke the
            // blob: URLs of this store's own layers, which are still wanted.
            this._teardownEngine();
            this.tracksLoading = true;
            this.loadedCount = 0;
            this.loadingTotal = this.layers.length;
            this.loadError = "";
            this.started = false;
            this.paused = false;
            const engine = new SoundscapeMixer();
            this._engine = engine;
            window.cosoundMixer = engine;
            engine.addEventListener("statechange", (event) => {
                emit("state", event.detail);
            });
            try {
                await engine.setLayers(this.layers.map(layerConfig), {
                    onProgress: ({ loaded, total }) => {
                        this.loadedCount = Math.round((loaded / total) * this.layers.length);
                        emit("progress", { loaded, total });
                    },
                });
                // A newer load — or the card being swapped out — tore this
                // engine down while its files decoded. Whatever replaced it
                // owns the loading state now, so this one leaves it alone.
                if (this._engine !== engine) return;
                this.loadedCount = this.layers.length;
                this._syncAllAnalysis();
                // The mix went to the engine as it stood before the files were
                // fetched. Anything moved while they loaded — a fader, a mute,
                // an Explore layer link isolating a layer from the writing
                // below the card — reached a voice that did not exist yet, so
                // push the layers' own state over the top of what was sent.
                this._syncAudibility();
                await settleProgress();
                if (this._engine !== engine) return;
                this.tracksLoading = false;
                emit("ready", { layers: this.layers.length });
            } catch (error) {
                if (this._engine !== engine) return;
                this.tracksLoading = false;
                this.loadError = error instanceof Error ? error.message : String(error);
                emit("error", { message: this.loadError });
                throw error;
            }
        },

        async playAll() {
            if (!this._engine || this.tracksLoading) return;
            await this._engine.play();
            this.started = true;
            this.paused = false;
        },
        async pause() {
            if (!this._engine) return;
            await this._engine.pause();
            this.paused = true;
        },
        async resume() {
            if (!this._engine) return;
            await this._engine.resume();
            this.paused = false;
        },
        masterVolumeUp() {
            this.layers.forEach((layer) => {
                layer.gain = Math.min(100, Number(layer.gain) + 10);
            });
            this._syncAudibility();
        },
        masterVolumeDown() {
            this.layers.forEach((layer) => {
                layer.gain = Math.max(0, Number(layer.gain) - 10);
            });
            this._syncAudibility();
        },

        /**
         * Append a layer to a running mix. `rawLayer` is either a serialized
         * library sound or a locally-built layer (see makeLocalLayer); the
         * engine treats a blob: URL exactly like an S3 one.
         */
        async addLayer(rawLayer) {
            if (!this._engine || !this.canAddLayer) return null;
            const layer = normalizeUiLayer(rawLayer);
            this.swappingLayer = false;
            this.loadError = "";
            const engine = this._engine;
            try {
                await engine.addLayer(layerConfig(layer));
                if (this._engine !== engine) return null;
                this.layers.push(layer);
                this.currentIndex = this.layers.length - 1;
                this._syncAnalysis(this.currentIndex);
                emit("add", { index: this.currentIndex, layer });
                return layer;
            } catch (error) {
                if (this._engine !== engine) return null;
                this.loadError = error instanceof Error ? error.message : String(error);
                emit("error", { message: this.loadError });
                throw error;
            }
        },

        /**
         * Make room for a sound without choosing one yet.
         *
         * Both `+` buttons come through here — the studio's tab and the one on
         * the layer indicator — so a blank layer means the same thing on either
         * surface. It holds a silent voice, which is what keeps the index
         * mapping between `layers` and the engine's voices one-to-one, and it
         * stops being blank the moment setLayerSource or replaceLayer gives it
         * audio.
         *
         * Resolves to the new layer, or to null when the mix cannot take one.
         */
        addBlankLayer() {
            return this.addLayer(makeDraftLayer());
        },

        /**
         * Drop a layer and keep `currentIndex` pointing at something real. A
         * local layer's blob: URLs are revoked here — this is the only place
         * that knows the layer is gone for good.
         */
        removeLayer(index) {
            const layer = this.layers[index];
            if (!layer || !this._engine) return;
            this._engine.removeLayer(index);
            this.layers.splice(index, 1);
            revokeLocalUrls(layer);
            if (this.currentIndex >= index) {
                this.currentIndex = Math.max(0, this.currentIndex - 1);
            }
            this._syncAudibility();
            emit("remove", { index, layer });
        },

        /**
         * Edit a layer's words — title, flavor, tags. Pure metadata, so the
         * audio graph is left alone.
         */
        updateLayer(index, patch) {
            const layer = this.layers[index];
            if (!layer) return;
            Object.assign(layer, patch);
            emit("update", { index, layer });
        },

        /**
         * Turn a blank layer into a new sound the artist is writing up. The
         * layer stays a draft — nothing has audio yet, so it is still left out
         * of a save — but it now carries an empty title, the artist's name,
         * stand-in artwork and an empty story, so the card reads like any
         * library sound whose words happen to be fields.
         *
         * The empty card's Create button calls this after it has faded the
         * card out, the same way a library pick lands behind the swap, and
         * raised `swappingLayer` for the wait. Lowering it here is what hands
         * the card back.
         */
        createSound(index) {
            const layer = this.layers[index];
            this.swappingLayer = false;
            if (!this.allowCreate || !layer?.isDraft || layer.isNew) return;
            this.updateLayer(index, {
                isNew: true,
                artwork_url: placeholderArtwork("New Sound"),
                // Empty, not "New Sound": the card shows that as the title
                // field's placeholder, beside a pencil that stays until the
                // artist types a title of their own.
                sound_title: "",
                sound_artist: this.artistName,
                flavor: "",
                tags: "",
                tag_list: [],
            });
        },

        /**
         * Give a new sound its audio from a file the artist picked. Picking
         * again swaps the file; the words, artwork and fader stay. The file
         * never leaves the tab — like a dropped track it is a blob: URL, so
         * the layer is local and kept out of a save.
         */
        async uploadSound(index, file) {
            const layer = this.layers[index];
            if (!layer?.isNew || !file) return null;
            const url = URL.createObjectURL(file);
            try {
                const next = await this.setLayerSource(index, {
                    sound_file: url,
                    sound_file_name: file.name,
                    is_local: true,
                });
                if (next) {
                    const files = newSoundFiles.get(layer.sound_id) ?? {};
                    newSoundFiles.set(next.sound_id, { ...files, audio: file });
                }
                return next;
            } catch (error) {
                URL.revokeObjectURL(url);
                throw error;
            }
        },

        /**
         * Give a new sound its artwork from a file the artist picked. Only the
         * picture changes, so the voice is left alone.
         */
        setArtwork(index, file) {
            const layer = this.layers[index];
            if (!layer?.isNew || !file) return;
            const previous = layer.artwork_url;
            const files = newSoundFiles.get(layer.sound_id) ?? {};
            newSoundFiles.set(layer.sound_id, { ...files, art: file });
            this.updateLayer(index, {
                artwork_url: URL.createObjectURL(file),
                artwork_file_name: file.name,
            });
            if (typeof previous === "string" && previous.startsWith("blob:")) {
                URL.revokeObjectURL(previous);
            }
        },

        /**
         * Make every new sound in the mix a real Sound, one POST each, and put
         * the finished layer in its place. The save dialog calls this just
         * before it saves the mix, and uses the answer to swap each new
         * sound's browser-made id in the posted layers for its real one.
         *
         * The swap keeps the voice that is already playing — the audio was
         * decoded from the blob, and it is the same audio — along with the
         * fader, mute, solo and the settings pane's timing. What changes is
         * that the layer is no longer new: its words stop being fields and
         * its files are the ones in storage. The server offers no edit, so
         * from here the sound is fixed.
         *
         * It stops at the first failure and throws the server's reason. The
         * sounds created before it stay created; a retry picks up the rest.
         *
         * @returns {Promise<Record<string, number>>} old id → Sound id
         */
        async createNewSounds(url, csrfToken) {
            const created = {};
            for (const current of [...this.layers]) {
                if (!current.isNew || current.isDraft) continue;
                const files = newSoundFiles.get(current.sound_id) ?? {};
                if (!files.audio || !files.art) {
                    throw new Error("Pick your new sound's file and artwork again.");
                }
                const body = new FormData();
                body.append("file", files.audio, current.sound_file_name || files.audio?.name);
                body.append("art", files.art, current.artwork_file_name || files.art?.name);
                body.append("title", current.sound_title ?? "");
                body.append("flavor", current.flavor ?? "");
                body.append("tags", (current.tag_list ?? []).join("\n"));
                const response = await fetch(url, {
                    method: "POST",
                    body,
                    headers: { "X-CSRFToken": csrfToken },
                    credentials: "same-origin",
                });
                const answer = await response.json().catch(() => ({}));
                if (!response.ok || !answer.layer) {
                    throw new Error(answer.error || "Your new sound could not be saved.");
                }
                const next = normalizeUiLayer({
                    ...current,
                    ...answer.layer,
                    // The server's layer comes at a default level; the
                    // artist's fader wins.
                    sound_gain: Number(current.gain) / 100,
                    mute: current.mute,
                    is_new: false,
                    isNew: false,
                    is_local: false,
                    isLocal: false,
                });
                next.isolated = current.isolated;
                const index = this.layers.indexOf(current);
                if (index === -1) continue;
                this.layers.splice(index, 1, next);
                revokeUnusedUrls(current, next);
                newSoundFiles.delete(current.sound_id);
                created[current.sound_id] = next.sound_id;
                emit("created", { index, layer: next });
            }
            return created;
        },

        /**
         * Set a new sound's tags. `tags` is the " / " string every card
         * reads; `tag_list` is the same thing kept as names for the editor.
         */
        setTags(index, names) {
            const unique = [...new Set(names)];
            this.updateLayer(index, { tag_list: unique, tags: unique.join(" / ") });
        },

        /**
         * Change how a layer is played back: its rate, the stretch factor that
         * spaces its two offset schedules, the crossfade each repeat overlaps
         * the next by, and the crop that decides which stretch of the file
         * either schedule plays.
         *
         * The engine bakes all of them into a voice's timing when it is
         * prepared, so there is no live setter — the voice has to be rebuilt.
         * replaceLayer does that against the same URL, and the engine's buffer
         * cache means nothing is refetched or re-decoded.
         */
        async setTiming(index, changes) {
            const layer = this.layers[index];
            if (!layer || !this._engine) return;
            const next = { ...layer, ...changes };
            const engine = this._engine;
            try {
                await engine.replaceLayer(index, layerConfig(next));
            } catch (error) {
                if (this._engine !== engine) return;
                throw error;
            }
            if (this._engine !== engine) return;
            Object.assign(layer, changes);
            this._syncAudibility();
            // After the crop, not before: a new region is a new loudness, and
            // the engine has just re-measured it.
            this._syncAnalysis(index);
            emit("timing", { index, layer });
        },

        /**
         * Give a layer its audio — the way a blank layer stops being blank, and
         * the way a local track's file is swapped. The artist's own words and
         * fader position survive; only the source changes.
         */
        async setLayerSource(index, source) {
            const current = this.layers[index];
            if (!current || !this._engine) return;
            const next = normalizeUiLayer({
                ...current,
                ...source,
                is_draft: false,
                isDraft: false,
                // The new source decides whether the layer is a browser-local
                // one, the same way it decides the file. A blank layer is
                // marked local because it has no Sound row either; a library
                // sound dropped into that slot must not inherit the mark, or
                // the mix it fills could never be saved.
                is_local: Boolean(source.is_local ?? source.isLocal),
                isLocal: Boolean(source.is_local ?? source.isLocal),
                // The artist's own page belongs to whoever made *this* file,
                // so it arrives with the source or not at all. Letting it fall
                // through from the layer being replaced is how a credit ends
                // up linking to a different artist's site — a local track
                // dropped over a library sound sends no artist at all.
                artist_url: source.artist_url ?? "",
                // A different file is a different length, so the crop the
                // artist set on the old one points into nothing. The loudness
                // target survives — it is a preference, not a measurement, and
                // the engine re-reads the new file against it.
                trim_start: 0,
                trim_end: null,
                duration: 0,
                loudness: null,
                loudness_gain_db: 0,
            });
            this.loadError = "";
            const engine = this._engine;
            try {
                await engine.replaceLayer(index, layerConfig(next));
                if (this._engine !== engine) return null;
                const [outgoing] = this.layers.splice(index, 1, next);
                revokeUnusedUrls(outgoing, next);
                this._syncAnalysis(index);
                emit("source", { index, layer: next });
                return next;
            } catch (error) {
                if (this._engine !== engine) return null;
                this.loadError = error instanceof Error ? error.message : String(error);
                emit("error", { message: this.loadError });
                throw error;
            }
        },

        async replaceLayer(index, rawLayer) {
            if (!this._engine) return;
            const layer = normalizeUiLayer(rawLayer);
            // Preserve the outgoing fader position so a search result does not
            // suddenly jump in level.
            layer.gain = Number(this.layers[index]?.gain ?? layer.gain);
            layer.mute = Boolean(this.layers[index]?.mute);
            layer.isolated = Boolean(this.layers[index]?.isolated);
            this.swappingLayer = true;
            this.swapLoading = true;
            this.loadError = "";
            const engine = this._engine;
            try {
                await Promise.all([
                    engine.replaceLayer(index, layerConfig(layer)),
                    preloadArtwork(layer.artwork_url),
                ]);
                if (this._engine !== engine) return;
                const [outgoing] = this.layers.splice(index, 1, layer);
                revokeUnusedUrls(outgoing, layer);
                this._syncAnalysis(index);
                emit("replace", { index, layer });
                await afterNextPaint();
            } catch (error) {
                if (this._engine !== engine) return;
                this.loadError = error instanceof Error ? error.message : String(error);
                emit("error", { message: this.loadError });
                throw error;
            } finally {
                this.swapLoading = false;
                this.swappingLayer = false;
            }
        },

        async loadMix(mix) {
            if (!this._engine) return;
            const nextLayers = mix.layers.map(normalizeUiLayer);
            this.tracksLoading = true;
            this.loadedCount = 0;
            this.loadingTotal = nextLayers.length;
            this.currentIndex = 0;
            this.loadError = "";
            const engine = this._engine;
            try {
                await engine.setLayers(nextLayers.map(layerConfig), {
                    onProgress: ({ loaded, total }) => {
                        this.loadedCount = Math.round((loaded / total) * nextLayers.length);
                    },
                });
                if (this._engine !== engine) return;
                this.layers.forEach(revokeLocalUrls);
                this.layers = nextLayers;
                this.loadedTitle = mix.title || "";
                this.loadedCount = nextLayers.length;
                this._syncAllAnalysis();
                await settleProgress();
                if (this._engine !== engine) return;
                this.tracksLoading = false;
                // Loading a saved mix is itself a playback gesture. The
                // AudioContext may still be suspended (or have been suspended
                // while the replacement files decoded), so replacing the
                // voices is not enough to make the new mix audible.
                await this.playAll();
                emit("mixload", { mix });
            } catch (error) {
                if (this._engine !== engine) return;
                this.tracksLoading = false;
                this.loadError = error instanceof Error ? error.message : String(error);
                emit("error", { message: this.loadError });
                throw error;
            }
        },

        _teardownEngine() {
            this._engine?.destroy();
            if (window.cosoundMixer === this._engine) {
                window.cosoundMixer = null;
            }
            this._engine = null;
        },

        destroy() {
            // A replacement tab can initialise before this store object is
            // overwritten. Clear playback state first so reactive consumers
            // never mistake the outgoing mix for a newly started one.
            this.started = false;
            this.paused = false;
            this._teardownEngine();
            this.layers.forEach(revokeLocalUrls);
        },
    };
}

let localLayerSequence = 0;

/**
 * An id for a browser-made layer that no server-made one can collide with.
 *
 * The studio opens on a blank layer the *server* seeded, and it arrives already
 * carrying `draft-1` (studio.views._blank_layer). A bare counter here would hand
 * that exact id to the first blank the artist adds, and both the tab strip and
 * the carousel run `x-for ... :key="l.sound_id"` — Alpine drops a duplicate key
 * rather than rendering it, so the layer would exist in the store with nothing
 * on screen and `+` would look dead. The timestamp segment keeps the two id
 * spaces apart; the counter keeps ids made within the same millisecond apart.
 */
function nextLocalId(prefix) {
    localLayerSequence += 1;
    return `${prefix}-${Date.now().toString(36)}-${localLayerSequence}`;
}

/**
 * Build a layer from files the artist picked on their own machine.
 *
 * The blob: URLs handed back are owned by the store from the moment the layer
 * is added — addLayer/removeLayer/destroy revoke them. Nothing here touches the
 * network: the file never leaves the tab, which is why the layer is marked
 * is_local and kept out of saved mixes.
 */
export function makeLocalLayer({ file, artworkFile = null, artistName = "" }) {
    if (!file) throw new Error("A local layer needs an audio file.");
    const title = file.name.replace(/\.[^.]+$/, "");
    return {
        sound_id: nextLocalId("local"),
        sound_file: URL.createObjectURL(file),
        sound_title: title,
        sound_artist: artistName,
        artwork_url: artworkFile
            ? URL.createObjectURL(artworkFile)
            : placeholderArtwork(title),
        gain: 50,
        mute: false,
        saved: false,
        flavor: "",
        tags: "your track",
        is_local: true,
    };
}

/**
 * An empty layer the artist fills in from the settings pane.
 *
 * It carries no audio, so the engine gives it a silent voice; the layer becomes
 * real once setLayerSource points it at a file or a library sound.
 */
export function makeDraftLayer() {
    const title = "";
    return {
        sound_id: nextLocalId("draft"),
        sound_file: "",
        sound_title: title,
        // No one owns the void.
        sound_artist: "",
        artwork_url: placeholderArtwork(title),
        gain: 50,
        mute: false,
        saved: false,
        flavor: "In the begining there was darkness.",
        tags: "Void",
        is_local: true,
        is_draft: true,
    };
}

export function mountSoundLayersStore(jsonElement, options = {}) {
    if (!jsonElement) throw new Error("The soundLayers JSON element is missing.");
    const layers = JSON.parse(jsonElement.textContent);
    const nextStore = createSoundLayersStore(layers, options);
    const currentStore = window.Alpine.store("soundLayers");
    currentStore?.destroy?.();
    window.Alpine.store("soundLayers", nextStore);
    const mountedStore = window.Alpine.store("soundLayers");
    mountedStore.initialize();
    return mountedStore;
}

export function installSoundscapeBridge() {
    const store = () => window.Alpine?.store("soundLayers");
    const handlers = {
        "cosound:audio:play": () => store()?.playAll(),
        "cosound:audio:pause": () => store()?.pause(),
        "cosound:audio:resume": () => store()?.resume(),
        "cosound:audio:replace-request": (event) => {
            const index = event.detail?.index ?? store()?.currentIndex;
            return store()?.replaceLayer(index, event.detail?.layer);
        },
        "cosound:audio:gain-request": (event) => {
            const activeStore = store();
            const layer = activeStore?.layers[event.detail?.index];
            if (layer) activeStore.setGain(layer, Number(event.detail.value) * 100);
        },
    };
    for (const [name, handler] of Object.entries(handlers)) {
        document.addEventListener(name, handler);
    }

    // When HTMX removes the mixer root, release its AudioContext and scheduled
    // BufferSourceNodes. A newly inserted mixer fragment mounts a fresh store.
    document.addEventListener("htmx:beforeCleanupElement", (event) => {
        const element = event.detail?.elt;
        if (element?.matches?.("[data-cosound-mixer-root]")
            || element?.querySelector?.("[data-cosound-mixer-root]")) {
            store()?.destroy();
        }
    });

    window.CosoundSoundscape = {
        SoundscapeMixer,
        createSoundLayersStore,
        mountStore: mountSoundLayersStore,
        makeLocalLayer,
        makeDraftLayer,
        dispatch(name, detail) {
            document.dispatchEvent(new CustomEvent(`cosound:audio:${name}`, { detail }));
        },
    };
}
