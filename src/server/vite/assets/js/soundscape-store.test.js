import test from "node:test";
import assert from "node:assert/strict";

// The store is browser code: it reaches for window, document and an
// AudioContext the moment it initialises. These stubs are the smallest surface
// that lets it run under node — nothing here makes sound, and the tests below
// only ever use blank layers, which the engine answers with a silent buffer
// rather than a fetch.
function fakeParam(value = 0) {
    return {
        value,
        maxValue: 1,
        setTargetAtTime() {},
        cancelScheduledValues() {},
        setValueAtTime(next) {
            this.value = next;
        },
        linearRampToValueAtTime(next) {
            this.value = next;
        },
    };
}

function fakeNode() {
    return {
        gain: fakeParam(),
        threshold: fakeParam(),
        knee: fakeParam(),
        ratio: fakeParam(),
        attack: fakeParam(),
        release: fakeParam(),
        connect: (destination) => destination,
        disconnect() {},
    };
}

/**
 * A twelve-second stereo tone standing in for a decoded file. A steady sine
 * referenced to full scale measures its own dBFS in LUFS, so `lufs` here is
 * both what the file holds and what the engine should read back out of it.
 */
function toneBuffer({ lufs = -33, seconds = 12, sampleRate = 48000 } = {}) {
    const length = Math.round(seconds * sampleRate);
    const amplitude = 10 ** (lufs / 20);
    const data = new Float32Array(length);
    for (let i = 0; i < length; i += 1) {
        data[i] = amplitude * Math.sin(2 * Math.PI * 1000 * i / sampleRate);
    }
    return {
        sampleRate,
        numberOfChannels: 2,
        length,
        duration: seconds,
        getChannelData: () => data,
    };
}

function fakeContext() {
    return {
        currentTime: 0,
        sampleRate: 44100,
        createBuffer: (channels, length, rate) => ({ duration: length / rate }),
        destination: fakeNode(),
        createGain: fakeNode,
        createChannelSplitter: fakeNode,
        createChannelMerger: fakeNode,
        createDynamicsCompressor: fakeNode,
        createBufferSource: fakeNode,
        decodeAudioData: async () => toneBuffer(),
        resume: async () => {},
        suspend: async () => {},
        close: async () => {},
    };
}

globalThis.window = globalThis;
globalThis.document = { dispatchEvent: () => true };
globalThis.AudioContext = function FakeAudioContext() {
    return fakeContext();
};
// Most tests here use blank layers, which the engine answers with a silent
// buffer rather than a fetch. The ones that need a length to crop or a level to
// measure need a layer with a file behind it, so both halves of the round trip
// are stubbed: nothing is transferred, and every URL decodes to the same tone.
globalThis.fetch = async () => ({
    ok: true,
    arrayBuffer: async () => new ArrayBuffer(8),
});

const { createSoundLayersStore, makeDraftLayer, MAX_LAYERS } = await import(
    "./soundscape-store.js"
);

// The blank layer library.utils.get_empty_layer opens the LIBRARY tab on. Its
// id is server-made and fixed, which is exactly what the client's ids have to
// dodge.
function seededBlankLayer() {
    return {
        sound_id: "draft-1",
        sound_file: "",
        sound_title: "",
        sound_artist: "",
        artwork_url: "",
        gain: 50,
        mute: false,
        saved: false,
        flavor: "In the begining there was darkness.",
        tags: "Void",
        is_local: true,
        is_draft: true,
    };
}

// A layer with a file behind it, the way a library sound or a dropped track
// arrives. Only these have a length to crop and a level to measure.
function soundLayer(overrides = {}) {
    return {
        sound_id: 9,
        sound_file: "/media/sounds/rain.ogg",
        sound_title: "Rain",
        gain: 50,
        mute: false,
        saved: true,
        flavor: "",
        tags: "rain",
        is_local: false,
        ...overrides,
    };
}

async function startedStore(rawLayers = [seededBlankLayer()], options = {}) {
    const store = createSoundLayersStore(rawLayers, options);
    await store.initialize();
    return store;
}

test("isolating a layer while the mix is still loading still silences the rest", async () => {
    // A layer link in an Explore post sits in the writing below the card, so a
    // reader can press one before the card has finished loading its files —
    // long before there is a voice for setLayerSolo to reach.
    const store = createSoundLayersStore(
        [soundLayer({ sound_id: 1 }), soundLayer({ sound_id: 2 })],
        { settleProgress: () => Promise.resolve() },
    );
    const loading = store.initialize();
    store.toggleIsolate(store.layers[1]);
    await loading;

    assert.deepEqual(
        store._engine.voices.map((voice) => voice.config.solo),
        [false, true],
    );
});

test("destroy clears playback state before a replacement store mounts", async () => {
    const store = await startedStore();
    store.started = true;
    store.paused = true;
    assert.equal(store.started, true);
    assert.equal(store.paused, true);

    store.destroy();

    assert.equal(store.started, false);
    assert.equal(store.paused, false);
});

test("a load torn down mid-decode leaves the loading state to the one that replaced it", async () => {
    // Each fetch waits until the test lets it through, so the first load can
    // finish decoding while the second is still waiting on its file.
    const releases = [];
    const fetchNow = globalThis.fetch;
    globalThis.fetch = () => new Promise((resolve) => {
        releases.push(() => resolve({ ok: true, arrayBuffer: async () => new ArrayBuffer(8) }));
    });
    try {
        const store = createSoundLayersStore([soundLayer()], {
            settleProgress: () => Promise.resolve(),
        });
        const first = store.initialize();
        const second = store.initialize();
        assert.equal(releases.length, 2);

        releases[0]();
        await first;

        assert.equal(store.tracksLoading, true);
        assert.equal(store.loadError, "");

        releases[1]();
        await second;

        assert.equal(store.tracksLoading, false);
        assert.equal(store._engine.voices.length, 1);
    } finally {
        globalThis.fetch = fetchNow;
    }
});

test("a mix swapped out while it loads neither errors nor reports ready", async () => {
    const store = createSoundLayersStore([soundLayer()], {
        settleProgress: () => Promise.resolve(),
    });
    const loading = store.initialize();

    store.destroy();
    await loading;

    assert.equal(store.loadError, "");
});

test("the loading view waits for its progress ring to finish at 100%", async () => {
    let releaseProgress;
    let progressReached;
    const reachedProgress = new Promise((resolve) => {
        progressReached = resolve;
    });
    const store = createSoundLayersStore([soundLayer()], {
        settleProgress: () => {
            progressReached();
            return new Promise((resolve) => {
                releaseProgress = resolve;
            });
        },
    });

    const initializing = store.initialize();
    await reachedProgress;

    assert.equal(store.loadedCount, 1);
    assert.equal(store.loadingTotal, 1);
    assert.equal(store.tracksLoading, true, "the 100% ring is still visible");

    releaseProgress();
    await initializing;
    assert.equal(store.tracksLoading, false);
});

test("loading a saved mix starts its replacement layers", async () => {
    const store = await startedStore();
    let playCalls = 0;
    store._engine.play = async () => {
        playCalls += 1;
    };

    await store.loadMix({ layers: [soundLayer()] });

    assert.equal(playCalls, 1);
    assert.equal(store.started, true);
    assert.equal(store.paused, false);
    assert.equal(store.layers[0].sound_title, "Rain");
});

test("a loaded mix keeps its name through edits", async () => {
    const store = await startedStore();
    store._engine.play = async () => {};

    await store.loadMix({ title: "Storm", layers: [soundLayer()] });
    assert.equal(store.loadedTitle, "Storm");

    // The name is what the save dialog opens on, and it has to survive the
    // editing it is there for: tweak a loaded Cosound and keeping the name is
    // what saves over it.
    await store.addLayer(makeDraftLayer());
    assert.equal(store.loadedTitle, "Storm");
});

test("a mix that was never saved has no name to open the dialog on", async () => {
    const store = await startedStore();
    store._engine.play = async () => {};

    assert.equal(store.loadedTitle, "");

    await store.loadMix({ layers: [soundLayer()] });
    assert.equal(store.loadedTitle, "");
});

test("a blank layer added in the browser cannot collide with the seeded one", async () => {
    const store = await startedStore();
    await store.addLayer(makeDraftLayer());

    assert.equal(store.layers.length, 2);
    // Both x-for loops that render layers — the tab strip and the carousel —
    // key on sound_id, and Alpine renders a duplicate key once. Two layers
    // sharing an id is the whole bug: the store grows, the screen does not.
    assert.notEqual(store.layers[0].sound_id, store.layers[1].sound_id);
    assert.equal(store.currentIndex, 1);
    assert.equal(store.layers[0].sound_title, "");
    assert.equal(store.layers[1].sound_title, "");
    assert.equal(store.layers[0].tags, "Void");
    assert.equal(store.layers[1].tags, "Void");
    assert.equal(store.layers[0].flavor, "In the begining there was darkness.");
    assert.equal(store.layers[1].flavor, "In the begining there was darkness.");
});

test("every browser-made layer gets its own id", async () => {
    const store = await startedStore();
    for (let i = 0; i < 5; i += 1) {
        await store.addLayer(makeDraftLayer());
    }
    const ids = store.layers.map((layer) => layer.sound_id);
    assert.equal(new Set(ids).size, ids.length);
});

test("a mix stops at MAX_LAYERS", async () => {
    const store = await startedStore();
    for (let i = store.layers.length; i < MAX_LAYERS; i += 1) {
        assert.notEqual(await store.addLayer(makeDraftLayer()), null);
    }

    assert.equal(store.layers.length, MAX_LAYERS);
    assert.equal(store.isFull, true);
    assert.equal(await store.addLayer(makeDraftLayer()), null);
    assert.equal(store.layers.length, MAX_LAYERS);
});

test("the + button's blank layer arrives selected, silent, marked and unowned", async () => {
    const store = await startedStore([], { artistName: "Some Artist" });
    const layer = await store.addBlankLayer();

    assert.equal(store.layers.length, 1);
    assert.equal(store.currentIndex, 0);
    assert.equal(store.currentLayer, layer);
    assert.equal(layer.isDraft, true);
    assert.equal(layer.sound_file, "");
    // No one owns the void.
    assert.equal(layer.sound_artist, "");
    // What every per-layer control reads to take itself out of service.
    assert.equal(store.currentIsDraft, true);
});

test("the + button goes away at the cap, and adding stops with it", async () => {
    const store = await startedStore();
    while (!store.isFull) {
        assert.equal(store.canAddLayer, true);
        assert.notEqual(await store.addBlankLayer(), null);
    }

    assert.equal(store.layers.length, MAX_LAYERS);
    assert.equal(store.canAddLayer, false);
    assert.equal(await store.addBlankLayer(), null);
    assert.equal(store.layers.length, MAX_LAYERS);
});

test("a mix mounted with adding switched off refuses every way in", async () => {
    const store = await startedStore([seededBlankLayer()], { allowAdd: false });

    assert.equal(store.canAddLayer, false);
    assert.equal(store.isFull, false);
    // Not just the blank-layer button: the library picker and a dropped file
    // both land on addLayer, and none of them may grow this mix.
    assert.equal(await store.addBlankLayer(), null);
    assert.equal(await store.addLayer(makeDraftLayer()), null);
    assert.equal(store.layers.length, 1);
});

test("filling a blank layer puts its controls back", async () => {
    const store = await startedStore();
    assert.equal(store.currentIsDraft, true);

    await store.setLayerSource(0, { sound_id: 7, sound_file: "", sound_title: "Rain" });

    assert.equal(store.currentIsDraft, false);
    assert.equal(store.layers[0].isDraft, false);
    assert.equal(store.layers[0].sound_title, "Rain");
    // The card stops greying a layer by its fader only while it is blank.
    assert.equal(store.grayscaleFor(store.layers[0]), 50);
});

test("a layer's artist page travels with its source, never from the layer before", async () => {
    // The carousel sends a press on the artist's name straight to this URL, so
    // a stale one is a credit pointing at somebody else's site. A new sound's
    // upload is the case that exposes it: it names no artist at all.
    const store = await startedStore([
        soundLayer({ artist_url: "https://cameron.example/" }),
    ]);
    assert.equal(store.layers[0].artist_url, "https://cameron.example/");

    await store.setLayerSource(0, {
        sound_file: "blob:local-track",
        sound_title: "My own take",
        is_local: true,
    });
    assert.equal(store.layers[0].artist_url, "");

    await store.setLayerSource(0, {
        sound_id: 12,
        sound_file: "/media/sounds/bell.ogg",
        sound_title: "Harbour Bell",
        artist_url: "https://sam.example/",
    });
    assert.equal(store.layers[0].artist_url, "https://sam.example/");
});

test("a mix of nothing but blank layers is an empty one to save", async () => {
    // The LIBRARY tab opens on a seeded blank layer, so this is what the save
    // button faces the moment the card loads.
    const store = await startedStore();
    await store.addBlankLayer();

    assert.equal(store.layers.length, 2);
    assert.deepEqual(store.savableLayers, []);
    assert.equal(store.canSave, false);
    assert.equal(store.saveBlockedReason, "Can't save empty Cosound.");
});

test("a blank layer alongside a sound neither blocks the save nor joins it", async () => {
    const store = await startedStore([soundLayer()]);
    await store.addBlankLayer();

    assert.equal(store.layers.length, 2);
    assert.equal(store.canSave, true);
    assert.equal(store.saveBlockedReason, "");
    // What the transport posts: the blank slot is simply not part of the mix.
    assert.deepEqual(
        store.savableLayers.map((layer) => layer.sound_id),
        [9],
    );
});

test("a track from the artist's own machine still blocks the save", async () => {
    // A blank layer is marked local too — it has no Sound row either — so this
    // is the check that skipping blanks did not take the local guard with it.
    const store = await startedStore([soundLayer({ is_local: true })]);

    assert.equal(store.canSave, false);
    assert.equal(
        store.saveBlockedReason,
        "Mixes with your own tracks stay on this device.",
    );
});

test("filling the last blank layer turns the save button on", async () => {
    const store = await startedStore();
    assert.equal(store.canSave, false);

    await store.setLayerSource(0, { sound_id: 7, sound_file: "", sound_title: "Rain" });

    assert.equal(store.canSave, true);
    assert.equal(store.saveBlockedReason, "");
});

test("the swapping screen stays up until audio and artwork are ready", async () => {
    let finishAudio;
    let finishArtwork;
    const PreviousImage = globalThis.Image;
    globalThis.Image = class PendingImage {
        set src(_value) {
            this.complete = false;
            finishArtwork = () => {
                this.complete = true;
                this.onload?.();
            };
        }
    };

    try {
        const store = await startedStore();
        store._engine.replaceLayer = () => new Promise((resolve) => {
            finishAudio = resolve;
        });
        const replacement = store.replaceLayer(0, soundLayer({
            artwork_url: "/media/art/rain.jpg",
        }));
        await Promise.resolve();

        assert.equal(store.swapLoading, true);
        assert.equal(store.swappingLayer, true);
        assert.equal(store.currentIsDraft, true);

        finishAudio();
        await Promise.resolve();
        assert.equal(store.swapLoading, true, "artwork is still pending");

        finishArtwork();
        await replacement;
        assert.equal(store.swapLoading, false);
        assert.equal(store.swappingLayer, false);
        assert.equal(store.currentLayer.sound_title, "Rain");
    } finally {
        globalThis.Image = PreviousImage;
    }
});

test("a decoded layer comes back knowing its own length", async () => {
    const store = await startedStore([soundLayer()]);

    // Nothing on the page can size a crop slider until this arrives, which is
    // why both new sections stay hidden while it is zero.
    assert.equal(store.layers[0].duration, 12);
    assert.equal(store.layers[0].trim_start, 0);
    assert.equal(store.layers[0].trim_end, 12);
    // A blank layer has no file, so it never offers a crop over one.
    const blank = await startedStore();
    assert.equal(blank.layers[0].duration, 0);
});

test("a crop is written back as the engine settled it, not as it was dragged", async () => {
    const store = await startedStore([soundLayer()]);

    await store.setTiming(0, { trim_start: 20, trim_end: 5 });

    // The start could not have 20 seconds; it takes the last quarter-second in
    // front of the end instead, and the slider snaps to say so.
    assert.equal(store.layers[0].trim_start, 4.75);
    assert.equal(store.layers[0].trim_end, 5);
});

test("a crossfade is written back as the engine settled it, not as it was asked for", async () => {
    const store = await startedStore([soundLayer()]);

    await store.setTiming(0, { loop_crossfade: 2 });

    assert.equal(store.layers[0].loop_crossfade, 2);
    // Half a pass is all a repeat can overlap of the one before it. The panel
    // reads that ceiling off the layer to size its slider.
    assert.equal(store.layers[0].loop_crossfade_max, 6);

    await store.setTiming(0, { loop_crossfade: 9 });

    assert.equal(store.layers[0].loop_crossfade, 6, "and the slider snaps to it");
});

test("a shorter crop cuts the crossfade down with it", async () => {
    const store = await startedStore([soundLayer()]);
    await store.setTiming(0, { loop_crossfade: 5 });

    await store.setTiming(0, { trim_start: 0, trim_end: 4 });

    assert.equal(store.layers[0].loop_crossfade_max, 2);
    assert.equal(store.layers[0].loop_crossfade, 2);
});

test("a new file clears the crop the old one was cut to", async () => {
    const store = await startedStore([soundLayer()]);
    await store.setTiming(0, { trim_start: 2, trim_end: 6 });

    await store.setLayerSource(0, {
        sound_id: 11,
        sound_file: "/media/sounds/wind.ogg",
        sound_title: "Wind",
    });

    assert.equal(store.layers[0].trim_start, 0);
    assert.equal(store.layers[0].trim_end, 12);
});

test("loudness matching reads the layer and reports its make-up gain", async () => {
    const store = await startedStore([soundLayer()]);
    assert.equal(store.layers[0].loudness_target, null, "off until asked for");
    assert.equal(store.layers[0].loudness_gain_db, 0);

    store.setLoudness(0, -23);

    assert.ok(Math.abs(store.layers[0].loudness + 33) < 0.1, "the tone is -33 LUFS");
    assert.ok(Math.abs(store.layers[0].loudness_gain_db - 10) < 0.1);

    store.setLoudness(0, null);

    assert.equal(store.layers[0].loudness_target, null);
    assert.equal(store.layers[0].loudness_gain_db, 0);
});

test("a loudness target survives being given a different file", async () => {
    const store = await startedStore([soundLayer()]);
    store.setLoudness(0, -20);

    await store.setLayerSource(0, {
        sound_id: 11,
        sound_file: "/media/sounds/wind.ogg",
        sound_title: "Wind",
    });

    // The target is a preference, so it carries; the reading is a measurement
    // of a file that is no longer there, so it is taken again.
    assert.equal(store.layers[0].loudness_target, -20);
    assert.ok(Math.abs(store.layers[0].loudness_gain_db - 13) < 0.1);
});

test("removing a layer from a full mix makes room again", async () => {
    const store = await startedStore();
    while (!store.isFull) {
        await store.addLayer(makeDraftLayer());
    }
    store.removeLayer(0);

    assert.equal(store.isFull, false);
    assert.notEqual(await store.addLayer(makeDraftLayer()), null);
    assert.equal(store.layers.length, MAX_LAYERS);
});

test("an emptied mix answers the fader's questions instead of throwing", async () => {
    // Deleting the last layer leaves the mix empty until its replacement blank
    // arrives, and the fader keeps asking about currentLayer the whole time.
    const store = await startedStore();
    store.removeLayer(0);

    assert.equal(store.currentLayer, undefined);
    assert.equal(store.isSilenced(store.currentLayer), false);
    assert.equal(store.grayscaleFor(store.currentLayer), 0);
});

test("Create turns a blank layer into a new sound that is still left out of a save", async () => {
    const store = await startedStore([seededBlankLayer()], {
        allowCreate: true,
        artistName: "Some Artist",
    });

    store.createSound(0);

    const layer = store.layers[0];
    assert.equal(layer.isNew, true);
    assert.equal(layer.isDraft, true);
    assert.equal(layer.sound_title, "");
    assert.equal(layer.sound_artist, "Some Artist");
    assert.equal(layer.flavor, "");
    assert.deepEqual(layer.tag_list, []);
    // No audio behind it yet, so there is still nothing to save.
    assert.equal(store.canSave, false);
});

test("Create gives the new sound stand-in artwork and hands the card back", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });
    const blankArtwork = store.layers[0].artwork_url;
    // The Create button raises this while it fades the card out.
    store.swappingLayer = true;

    store.createSound(0);

    assert.match(store.layers[0].artwork_url, /^data:image\/svg\+xml,/);
    assert.notEqual(store.layers[0].artwork_url, blankArtwork);
    assert.equal(store.swappingLayer, false);
});

test("Create is refused without allowCreate, and on a layer that has a sound", async () => {
    const plain = await startedStore([seededBlankLayer()]);
    plain.createSound(0);
    assert.equal(plain.layers[0].isNew, false);

    const filled = await startedStore([soundLayer()], { allowCreate: true });
    filled.createSound(0);
    assert.equal(filled.layers[0].isNew, false);
    assert.equal(filled.layers[0].sound_title, "Rain");
});

test("a new sound's tags keep the list and the card's string in step", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });
    store.createSound(0);

    store.setTags(0, ["rain", "night", "rain"]);

    assert.deepEqual(store.layers[0].tag_list, ["rain", "night"]);
    assert.equal(store.layers[0].tags, "rain / night");
});

test("filling a new sound from the library makes it an ordinary layer again", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });
    store.createSound(0);

    await store.replaceLayer(0, soundLayer());

    assert.equal(store.layers[0].isNew, false);
    assert.equal(store.layers[0].isDraft, false);
});

test("uploading a sound gives a new sound audio and keeps its words", async () => {
    const store = await startedStore([seededBlankLayer()], {
        allowCreate: true,
        artistName: "Some Artist",
    });
    store.createSound(0);
    store.updateLayer(0, { sound_title: "Harbour" });

    await store.uploadSound(0, new File(["x"], "harbour-at-dawn.wav"));

    const layer = store.layers[0];
    assert.equal(layer.isNew, true);
    assert.equal(layer.isDraft, false);
    assert.equal(layer.isLocal, true);
    assert.ok(layer.sound_file.startsWith("blob:"));
    assert.equal(layer.sound_file_name, "harbour-at-dawn.wav");
    assert.equal(layer.sound_title, "Harbour");
    assert.equal(layer.sound_artist, "Some Artist");
    // It has no artwork yet, so it is not ready to become a Sound.
    assert.equal(store.canSave, false);
    assert.equal(store.saveBlockedReason, "Your new sound needs artwork.");

    const first = layer.sound_file;
    await store.uploadSound(0, new File(["y"], "second-take.wav"));
    assert.equal(store.layers[0].sound_file_name, "second-take.wav");
    assert.notEqual(store.layers[0].sound_file, first);
});

test("uploads are refused on a layer that is not a new sound", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });

    assert.equal(await store.uploadSound(0, new File(["x"], "a.wav")), null);
    store.setArtwork(0, new File(["x"], "a.png"));

    assert.equal(store.layers[0].isDraft, true);
    assert.equal(store.layers[0].sound_file_name, undefined);
    assert.equal(store.layers[0].artwork_file_name, undefined);
});

test("artwork on a new sound is swapped without touching its audio", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });
    store.createSound(0);
    await store.uploadSound(0, new File(["x"], "take.wav"));
    const sound = store.layers[0].sound_file;

    store.setArtwork(0, new File(["x"], "cover.png"));
    const cover = store.layers[0].artwork_url;
    store.setArtwork(0, new File(["y"], "cover-2.png"));

    assert.ok(cover.startsWith("blob:"));
    assert.notEqual(store.layers[0].artwork_url, cover);
    assert.equal(store.layers[0].artwork_file_name, "cover-2.png");
    assert.equal(store.layers[0].sound_file, sound);
});

async function readyNewSound(store, index = 0) {
    store.createSound(index);
    store.updateLayer(index, { sound_title: "Harbour", flavor: "Gulls." });
    store.setTags(index, ["sea", "birds"]);
    await store.uploadSound(index, new File(["x"], "harbour.wav"));
    store.setArtwork(index, new File(["y"], "harbour.png"));
}

test("a new sound blocks the save until it has a file, a title and artwork", async () => {
    const store = await startedStore([soundLayer(), seededBlankLayer()], {
        allowCreate: true,
    });
    store.createSound(1);
    // Still a draft, so not in the save — but saving past it would lose it.
    assert.equal(store.canSave, false);
    assert.equal(store.saveBlockedReason, "Your new sound needs a sound file.");

    await store.uploadSound(1, new File(["x"], "take.wav"));
    assert.equal(store.saveBlockedReason, "Your new sound needs a title.");

    store.updateLayer(1, { sound_title: "Take" });
    assert.equal(store.saveBlockedReason, "Your new sound needs artwork.");

    store.setArtwork(1, new File(["y"], "take.png"));
    assert.equal(store.canSave, true);
    assert.equal(store.saveBlockedReason, "");
    assert.deepEqual(
        store.saveLayers.map((layer) => layer.is_new ?? false),
        [false, true],
    );
});

test("a dropped track still keeps the mix on this device", async () => {
    const store = await startedStore([soundLayer({ sound_id: "local-1", is_local: true })]);
    assert.equal(store.canSave, false);
    assert.equal(store.saveBlockedReason, "Mixes with your own tracks stay on this device.");
});

test("createNewSounds posts each new sound and swaps in the finished layer", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });
    await readyNewSound(store);
    store.setGain(store.layers[0], 80);
    const oldId = store.layers[0].sound_id;

    const posted = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url, init) => {
        posted.push({ url, init });
        return {
            ok: true,
            json: async () => ({
                layer: {
                    sound_id: 42,
                    sound_file: "/media/sounds/harbour.wav",
                    sound_gain: 0.5,
                    gain: 50,
                    sound_title: "Harbour",
                    sound_artist: "Some Artist",
                    artwork_url: "/media/sound_arts/harbour.png",
                    published: false,
                    tags: "sea / birds",
                },
            }),
        };
    };
    try {
        const created = await store.createNewSounds("/library/sounds/create/", "token");
        assert.deepEqual(created, { [oldId]: 42 });
    } finally {
        globalThis.fetch = original;
    }

    const posts = posted.filter(({ init }) => init?.method === "POST");
    assert.equal(posts.length, 1);
    assert.equal(posts[0].init.headers["X-CSRFToken"], "token");
    // And the voice moves over to the file that was stored.
    assert.ok(posted.some(({ url }) => url === "/media/sounds/harbour.wav"));
    const body = posts[0].init.body;
    assert.equal(body.get("title"), "Harbour");
    assert.equal(body.get("flavor"), "Gulls.");
    assert.equal(body.get("tags"), "sea\nbirds");
    assert.equal(body.get("file").name, "harbour.wav");
    assert.equal(body.get("art").name, "harbour.png");
    // The loop check rides along, for the server to bake into the file.
    assert.equal(body.get("trim_start"), "0");
    assert.equal(body.get("loop_crossfade"), "0");
    assert.equal(body.get("loudness_target"), "-20");

    const layer = store.layers[0];
    assert.equal(layer.sound_id, 42);
    assert.equal(layer.isNew, false);
    assert.equal(layer.isLocal, false);
    assert.equal(layer.published, false);
    // The artist's fader survives; the server's default level does not.
    assert.equal(layer.gain, 80);
    // It goes on playing the way it was checked: one copy, back to back.
    assert.deepEqual(store.saveLayers, [{
        sound_id: 42,
        sound_gain: 0.8,
        playback_rate: 1,
        stretch: 1,
        second_copy: false,
        repetitions: 1,
        cycle_rest: 0,
        start_delay: 0,
        phase_step: 0,
        phase_hold: 4,
        phase_hold_alt: 4,
        playback_rate_b: null,
        take_turns: false,
        turn_gap: 0,
    }]);
});

test("createNewSounds reports the server's reason and leaves the sound new", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });
    await readyNewSound(store);

    const original = globalThis.fetch;
    globalThis.fetch = async () => ({
        ok: false,
        json: async () => ({ error: "Sound must be 50 MB or smaller." }),
    });
    try {
        await assert.rejects(
            store.createNewSounds("/library/sounds/create/", "token"),
            /50 MB/,
        );
    } finally {
        globalThis.fetch = original;
    }
    assert.equal(store.layers[0].isNew, true);
    assert.equal(store.canSave, true);
});

test("Create puts a new sound into its loop check", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });

    store.createSound(0);

    const layer = store.layers[0];
    // One copy, back to back, nothing held back — so the seam is what is heard.
    assert.equal(layer.stretch, 1);
    assert.equal(layer.second_copy, false);
    assert.equal(layer.playback_rate, 1);
    assert.equal(layer.cycle_rest, 0);
    assert.equal(layer.start_delay, 0);
    assert.equal(layer.phase_step, 0);
    assert.equal(layer.loop_crossfade, 0);
    // Levelled to the house loudness from the first file it is given.
    assert.equal(layer.loudness_target, store.loudnessDefault);
    assert.equal(store.loudnessDefault, -20);
});

test("uploading keeps the loop check the new sound was put into", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });
    store.createSound(0);

    await store.uploadSound(0, new File(["x"], "harbour.wav"));

    const layer = store.layers[0];
    assert.equal(layer.stretch, 1);
    assert.equal(layer.second_copy, false);
    assert.equal(layer.loudness_target, -20);
    assert.equal(store._engine.voices[0].config.secondCopy, false);
});

test("createNewSounds sends the crop, crossfade and loudness, then clears them", async () => {
    const store = await startedStore([seededBlankLayer()], { allowCreate: true });
    await readyNewSound(store);
    await store.setTiming(0, { trim_start: 1, trim_end: 5, loop_crossfade: 0.5 });
    const reading = store.layers[0].loudness;

    const posted = [];
    const original = globalThis.fetch;
    globalThis.fetch = async (url, init) => {
        posted.push(init);
        if (init?.method !== "POST") return original(url, init);
        return {
            ok: true,
            json: async () => ({
                layer: {
                    sound_id: 42,
                    sound_file: "/media/sounds/harbour.flac",
                    sound_title: "Harbour",
                    artwork_url: "/media/sound_arts/harbour.png",
                    seamless: true,
                    loudness_lufs: -20,
                },
            }),
        };
    };
    try {
        await store.createNewSounds("/library/sounds/create/", "token");
    } finally {
        globalThis.fetch = original;
    }

    const body = posted[0].body;
    assert.equal(body.get("trim_start"), "1");
    assert.equal(body.get("trim_end"), "5");
    assert.equal(body.get("loop_crossfade"), "0.5");
    assert.equal(body.get("loudness"), String(reading));

    const layer = store.layers[0];
    // The file carries all three now; set again, they would apply twice.
    assert.equal(layer.trim_start, 0);
    assert.equal(layer.trim_end, null);
    assert.equal(layer.loop_crossfade, 0);
    assert.equal(layer.loudness_target, null);
    assert.equal(layer.seamless, true);
    assert.equal(layer.loudness_lufs, -20);
    // And it plays on as it was checked.
    assert.equal(layer.stretch, 1);
    assert.equal(layer.second_copy, false);
});

test("a seamless sound from the picker starts as one copy, back to back", async () => {
    const store = await startedStore([
        soundLayer({ sound_id: 1, seamless: true }),
        soundLayer({ sound_id: 2 }),
        soundLayer({ sound_id: 3, seamless: true, stretch: 2, second_copy: true }),
    ]);
    const [loop, older, saved] = store.layers;

    assert.equal(loop.stretch, 1);
    assert.equal(loop.second_copy, false);
    assert.equal(older.stretch, 1.75, "an unbaked sound keeps its two drifting copies");
    assert.equal(older.second_copy, true);
    assert.equal(saved.stretch, 2, "a saved mix's own timing wins");
    assert.equal(saved.second_copy, true);
    assert.equal(store._engine.voices[0].config.seamless, true);
});

test("saveLayers carries each layer's timing, and nothing of the card's", async () => {
    const store = await startedStore([soundLayer({
        cycle_rest: 12, repetitions: 3, start_delay: 4,
        phase_step: 0.125, phase_hold: 2, phase_hold_alt: 5,
        playback_rate_b: 0.5, take_turns: true, turn_gap: 1.5,
    })]);
    store.toggleSettings(0);

    assert.deepEqual(store.saveLayers, [{
        sound_id: 9,
        sound_gain: 0.5,
        playback_rate: 1,
        stretch: 1.75,
        second_copy: true,
        repetitions: 3,
        cycle_rest: 12,
        start_delay: 4,
        phase_step: 0.125,
        phase_hold: 2,
        phase_hold_alt: 5,
        playback_rate_b: 0.5,
        take_turns: true,
        turn_gap: 1.5,
    }]);
});

test("a layer's settings stay open while the carousel is elsewhere", async () => {
    const store = await startedStore([soundLayer({ sound_id: 1 }), soundLayer({ sound_id: 2 })]);

    store.toggleSettings(0);
    store.currentIndex = 1;
    assert.equal(store.layers[0].settingsOpen, true);
    assert.equal(store.layers[1].settingsOpen, false);
    store.currentIndex = 0;
    assert.equal(store.currentLayer.settingsOpen, true);

    store.toggleSettings(0);
    assert.equal(store.layers[0].settingsOpen, false);
});

test("the gear is an artist's, on a mix they can edit", async () => {
    assert.equal((await startedStore()).canTune, false);
    assert.equal((await startedStore(undefined, { allowCreate: true })).canTune, true);
    assert.equal(
        (await startedStore(undefined, { allowCreate: true, allowAdd: false })).canTune,
        false,
    );
});

test("timing changes hand the layer over in place instead of restarting it", async () => {
    const store = await startedStore([soundLayer()]);
    const retimed = [];
    const restarted = [];
    const retime = store._engine.retimeLayer.bind(store._engine);
    store._engine.retimeLayer = (index, config, options) => {
        retimed.push(config);
        return retime(index, config, options);
    };
    store._engine.replaceLayer = (...args) => restarted.push(args);

    await store.setTiming(0, { stretch: 2 });
    await store.setTiming(0, { start_delay: 6 });

    assert.deepEqual(retimed.map((config) => [config.stretch, config.startDelay]), [[2, 0], [2, 6]]);
    assert.deepEqual(restarted, [], "no edit starts the layer over");
    assert.equal(store.layers[0].start_delay, 6);
});

test("a seek starts the mix if it has not started, then moves the layer", async () => {
    const store = await startedStore([soundLayer()], { settleProgress: () => Promise.resolve() });
    const calls = [];
    store._engine.play = async () => calls.push("play");
    store._engine.seekLayer = async (index, position) => calls.push(["seek", index, position]);

    await store.seek(0, 4.5);
    assert.deepEqual(calls, ["play", ["seek", 0, 4.5]]);
    assert.equal(store.started, true);

    await store.seek(0, 1);
    assert.deepEqual(calls.at(-1), ["seek", 0, 1], "a playing mix is not started again");
    assert.equal(calls.filter((call) => call === "play").length, 1);
});

test("hear the seam lands just ahead of where the crossfade begins", async () => {
    const store = await startedStore([soundLayer()], { settleProgress: () => Promise.resolve() });
    const seeks = [];
    store.started = true;
    store._engine.seekLayer = async (index, position) => seeks.push(position);

    // The tone is 12s; a 0.5s fade starts at 11.5, and two seconds before that
    // is 9.5.
    await store.setTiming(0, { loop_crossfade: 0.5 });
    await store.hearSeam(0);
    // At double speed those two seconds cover twice as much of the file.
    await store.setTiming(0, { playback_rate: 2 });
    await store.hearSeam(0);
    // A crop keeps the jump inside what is kept.
    await store.setTiming(0, { playback_rate: 1, trim_start: 10, trim_end: 11 });
    await store.hearSeam(0);

    assert.deepEqual(seeks.map((s) => Math.round(s * 1000) / 1000), [9.5, 7, 10]);
});
