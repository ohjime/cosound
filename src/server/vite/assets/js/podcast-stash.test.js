import test from 'node:test';
import assert from 'node:assert/strict';
import { createPodcastStash, formatPodcastTime, MAX_PODCASTS } from './podcast-stash.js';
import { DEFAULT_PODCAST_EFFECTS, PODCAST_PRESETS } from './podcast-effects.js';

const episode = index => ({ id: String(index), title: `Episode ${index}`, audio_url: `https://podcasts.example/${index}.mp3` });
function setup(options = {}) {
    let callbacks;
    const calls = [];
    const player = {
        load(item, settings) { calls.push(['load', item, settings]); return Promise.resolve(true); },
        play() { calls.push(['play']); }, pause() { calls.push(['pause']); },
        setVolume(value) { calls.push(['volume', value]); },
        setPreset(value) { calls.push(['preset', value]); },
        setEffectMix(value) { calls.push(['effectMix', value]); },
        setTexture(value) { calls.push(['texture', value]); },
        setSpace(value) { calls.push(['space', value]); },
        seek(value) { calls.push(['seek', value]); }, destroy() { calls.push(['destroy']); },
    };
    const stash = createPodcastStash({
        eventTarget: new EventTarget(),
        playerFactory: value => { callbacks = value; return player; },
        ...options,
    });
    stash.$el = options.element;
    stash.init();
    return { stash, calls, callbacks };
}

test('queue plays one episode at a time, advances on end, and stops at the end', async () => {
    const { stash, calls, callbacks } = setup();
    stash.add(episode(1)); stash.add(episode(2));
    assert.equal(calls.length, 0, 'adding episodes does not download audio');
    await stash.togglePlayback();
    assert.equal(calls.at(-1)[1].id, '1', 'adding several episodes starts with the first');
    callbacks.onEnded();
    assert.equal(stash.activeIndex, 1);
    assert.equal(calls.at(-1)[1].id, '2');
    assert.equal(calls.at(-1)[2].autoplay, true);
    const length = calls.length;
    callbacks.onEnded();
    assert.equal(calls.length, length, 'queue does not loop');
    stash.destroy();
});

test('selected settings belong to each episode without changing the one playing', async () => {
    const { stash, calls } = setup();
    stash.add(episode(1)); stash.add(episode(2));
    await stash.playAt(0);
    stash.select(1); stash.setVolume(.25); stash.setPreset('vintage');
    stash.setEffectMix(.9); stash.setTexture(.3); stash.setSpace(.4);
    assert.equal(calls.length, 1);
    await stash.playAt(1);
    assert.deepEqual(calls.at(-1)[2], {
        autoplay: true, volume: .25, preset: 'vintage', effectMix: .9, texture: .3, space: .4,
    });
    stash.setVolume(.5); stash.setPreset('radio');
    stash.setEffectMix(.6); stash.setTexture(.2); stash.setSpace(.1);
    assert.deepEqual(calls.slice(-5), [
        ['volume', .5], ['preset', 'radio'], ['effectMix', .6], ['texture', .2], ['space', .1],
    ]);
    assert.equal(calls.filter(([action]) => action === 'load').length, 2, 'live settings never reload the episode');
    assert.equal(stash.queue[0].preset, 'clean');
    assert.equal(stash.queue[0].texture, DEFAULT_PODCAST_EFFECTS.texture);
    stash.destroy();
});

test('all catalog effects can be selected without autoplay, and unknown effects are ignored', async () => {
    const { stash, calls } = setup();
    stash.add(episode(1));
    assert.deepEqual(stash.presets, PODCAST_PRESETS);
    for (const preset of stash.presets) {
        stash.setPreset(preset.id);
        assert.equal(stash.selected.preset, preset.id);
        assert.equal(stash.selectedPreset.id, preset.id);
    }
    const previous = stash.selected.preset;
    stash.setPreset('unknown');
    await stash.auditionPreset('unknown');
    assert.equal(stash.selected.preset, previous);
    assert.equal(calls.length, 0, 'selecting a sound or rejecting an invalid audition never starts audio');
    stash.destroy();
});

test('effect sliders clamp out-of-range values and preserve settings on invalid input', () => {
    const { stash, calls } = setup();
    stash.add(episode(1));
    stash.setEffectMix('2'); stash.setTexture(-1); stash.setSpace('0.42');
    assert.equal(stash.selected.effectMix, 1);
    assert.equal(stash.selected.texture, 0);
    assert.equal(stash.selected.space, .42);
    stash.setEffectMix(NaN); stash.setTexture(Infinity); stash.setSpace('invalid');
    assert.equal(stash.selected.effectMix, 1);
    assert.equal(stash.selected.texture, 0);
    assert.equal(stash.selected.space, .42);
    assert.equal(calls.length, 0, 'configuring a queued episode does not touch active audio');
    stash.destroy();
});

test('audition starts a queued episode, resumes a paused one, and never restarts playing or loading audio', async () => {
    const { stash, calls, callbacks } = setup();
    stash.add(episode(1)); stash.add(episode(2));
    await stash.auditionPreset('noir');
    assert.equal(calls.at(-1)[0], 'load');
    assert.equal(calls.at(-1)[2].preset, 'noir');
    assert.equal(calls.at(-1)[2].autoplay, true);
    callbacks.onChange({ playing: true, currentTime: 52 });
    await stash.auditionPreset('cassette');
    assert.deepEqual(calls.at(-1), ['preset', 'cassette']);
    assert.equal(stash.status.currentTime, 52);
    callbacks.onChange({ playing: false, loading: true });
    await stash.auditionPreset('telephone');
    assert.deepEqual(calls.at(-1), ['preset', 'telephone']);
    assert.equal(calls.filter(([action]) => action === 'play' || action === 'load').length, 1);
    callbacks.onChange({ loading: false });
    await stash.auditionPreset('newsreel');
    assert.deepEqual(calls.at(-1), ['play']);
    assert.equal(calls.filter(([action]) => action === 'load').length, 1, 'resuming does not reload');
    stash.select(1);
    await stash.auditionPreset('gramophone');
    assert.equal(calls.at(-1)[1].id, '2');
    assert.equal(calls.at(-1)[2].preset, 'gramophone');
    stash.destroy();
});

test('reset returns selected effects to Original and defaults without restarting audio or changing its volume', async () => {
    const { stash, calls, callbacks } = setup();
    stash.add(episode(1)); stash.add(episode(2));
    stash.setPreset('shortwave'); stash.setEffectMix(.2); stash.setTexture(.8); stash.setSpace(.6);
    stash.setVolume(.35);
    await stash.playAt(0);
    callbacks.onChange({ playing: true, currentTime: 80 });
    const beforeReset = calls.length;
    stash.resetEffects();
    assert.equal(stash.selected.preset, 'clean');
    for (const [key, value] of Object.entries(DEFAULT_PODCAST_EFFECTS)) assert.equal(stash.selected[key], value);
    assert.equal(stash.selected.volume, .35);
    assert.equal(stash.status.currentTime, 80);
    assert.deepEqual(calls.slice(beforeReset), [
        ['preset', 'clean'], ['effectMix', DEFAULT_PODCAST_EFFECTS.effectMix],
        ['texture', DEFAULT_PODCAST_EFFECTS.texture], ['space', DEFAULT_PODCAST_EFFECTS.space],
    ]);
    stash.select(1); stash.setPreset('fireside'); stash.setSpace(.9);
    const beforeQueuedReset = calls.length;
    stash.resetEffects();
    assert.equal(stash.selected.preset, 'clean');
    assert.equal(stash.selected.space, DEFAULT_PODCAST_EFFECTS.space);
    assert.equal(calls.length, beforeQueuedReset, 'resetting another episode leaves current audio alone');
    stash.destroy();
});

test('publisher effects fallback preserves ordinary playback and only disables the active episode controls', async () => {
    const { stash, calls, callbacks } = setup();
    stash.add(episode(1)); stash.add(episode(2));
    stash.setPreset('radio');
    await stash.playAt(0);
    callbacks.onChange({ playing: true, effectsAvailable: false, currentTime: 10, notice: 'Original audio only.' });
    assert.equal(stash.effectsBlocked, true);
    assert.equal(stash.status.playing, true);
    assert.equal(stash.selected.preset, 'radio', 'publisher fallback does not discard chosen effects');
    await stash.togglePlayback();
    assert.deepEqual(calls.at(-1), ['pause'], 'regular transport remains available');
    callbacks.onChange({ playing: false });
    await stash.togglePlayback();
    assert.deepEqual(calls.at(-1), ['play']);
    stash.select(1);
    assert.equal(stash.effectsBlocked, false, 'a different episode can be configured before it plays');
    stash.setPreset('fireside'); stash.setTexture(.4);
    assert.equal(stash.selected.preset, 'fireside');
    callbacks.onChange({ effectsAvailable: true });
    stash.select(0);
    assert.equal(stash.effectsBlocked, false);
    stash.destroy();
});

test('reordering keeps active and selected episodes stable and changes what follows', async () => {
    const { stash, calls, callbacks } = setup();
    [1, 2, 3].forEach(index => stash.add(episode(index)));
    await stash.playAt(0);
    stash.select(2); stash.setPreset('noir'); stash.setEffectMix(.8); stash.setTexture(.25); stash.setSpace(.55);
    stash.move(2, -1);
    assert.equal(stash.activeIndex, 0);
    assert.equal(stash.selected.id, '3');
    callbacks.onEnded();
    assert.equal(calls.at(-1)[1].id, '3');
    assert.deepEqual(calls.at(-1)[2], {
        autoplay: true, volume: .75, preset: 'noir', effectMix: .8, texture: .25, space: .55,
    });
    stash.destroy();
});

test('removing active playback starts its successor; removing final media releases it', async () => {
    const { stash, calls, callbacks } = setup();
    [1, 2].forEach(index => stash.add(episode(index)));
    await stash.playAt(0);
    callbacks.onChange({ playing: true });
    stash.remove(0);
    assert.equal(stash.activeIndex, 0);
    assert.equal(calls.at(-1)[1].id, '2');
    stash.remove(0);
    assert.equal(stash.activeId, null);
    assert.equal(calls.at(-1)[1], null);
    assert.equal(stash.queue.length, 0);
    stash.destroy();
});

test('closing drawer preserves playback but leaving library destroys it exactly once', () => {
    const { stash, calls, callbacks } = setup();
    stash.add(episode(1)); stash.open = true; stash.toggleDrawer();
    assert.equal(calls.length, 0);
    stash.destroy(); stash.destroy();
    callbacks.onEnded(); callbacks.onChange({ playing: true });
    assert.deepEqual(calls, [['destroy']]);
    assert.equal(stash.status.playing, false);
});

test('removing the podcast card keeps progress and effects, advances while hidden, and reopens without reloading audio', async () => {
    const { stash, calls, callbacks } = setup();
    stash.add(episode(1)); stash.add(episode(2));
    stash.setPreset('radio');
    stash.setEffectMix(.65); stash.setTexture(.3); stash.setSpace(.2);
    stash.select(1); stash.setPreset('cassette'); stash.setEffectMix(.85); stash.setTexture(.2); stash.setSpace(.45);
    stash.panel = 'queue';
    stash.toggleDrawer();
    await stash.playAt(0);
    callbacks.onChange({ playing: true, currentTime: 120 });
    const beforeClose = calls.length;
    stash.cardRemoved({ dataset: { cardKey: 'library-podcasts' } });
    assert.equal(stash.open, false);
    assert.equal(stash.status.playing, true);
    assert.equal(stash.status.currentTime, 120);
    assert.equal(stash.selected.preset, 'radio');
    assert.equal(stash.selected.effectMix, .65);
    assert.equal(stash.selected.texture, .3);
    assert.equal(stash.selected.space, .2);
    assert.equal(calls.length, beforeClose, 'closing the presentation does not touch media');
    callbacks.onEnded();
    assert.equal(stash.activeIndex, 1);
    assert.deepEqual(calls.at(-1)[2], {
        autoplay: true, volume: .75, preset: 'cassette', effectMix: .85, texture: .2, space: .45,
    });
    assert.equal(stash.open, false, 'next episode does not reopen the card');
    const beforeReopen = calls.length;
    stash.toggleDrawer();
    assert.equal(stash.open, true);
    assert.equal(stash.panel, 'queue');
    assert.equal(stash.queue.length, 2);
    assert.equal(calls.length, beforeReopen, 'reopening does not reload or restart media');
    stash.destroy();
});

test('a different card removal or a stale exit cannot close a newly reopened podcast card', () => {
    const { stash } = setup({ element: { querySelector: () => ({ id: 'podcast-drawer' }) } });
    stash.open = true;
    stash.cardRemoved({ dataset: { cardKey: 'library-liked' } });
    assert.equal(stash.open, true);
    stash.cardRemoved({ dataset: { cardKey: 'library-podcasts' } });
    assert.equal(stash.open, true);
    stash.destroy();
});

test('HTMX removing a child card leaves playback alive; removing its Library owner stops it', () => {
    const eventTarget = new EventTarget();
    const owner = { contains: () => false };
    const { stash, calls } = setup({ eventTarget, element: owner });
    eventTarget.dispatchEvent(new CustomEvent('htmx:beforeCleanupElement', {
        detail: { elt: { contains: () => false } },
    }));
    assert.equal(calls.length, 0);
    eventTarget.dispatchEvent(new CustomEvent('htmx:beforeCleanupElement', { detail: { elt: owner } }));
    assert.deepEqual(calls, [['destroy']]);
    stash.destroy();
});

test('queue bounds and duplicate enclosures do not create extra entries', () => {
    const { stash } = setup();
    stash.add(episode(0)); stash.add(episode(0));
    assert.equal(stash.queue.length, 1);
    for (let i = 1; i < MAX_PODCASTS + 3; i++) stash.add(episode(i));
    assert.equal(stash.queue.length, MAX_PODCASTS);
    assert.equal(stash.full, true);
    stash.destroy();
});

test('older searches cannot overwrite a newer result, even if fetch ignores abort', async () => {
    const waiting = [];
    const { stash } = setup({ fetcher: () => new Promise(resolve => waiting.push(resolve)) });
    stash.query = 'first'; const first = stash.search();
    stash.queryChanged(); stash.query = 'second'; const second = stash.search();
    waiting[1]({ ok: true, json: async () => ({ shows: [{ title: 'Second' }] }) });
    await second;
    waiting[0]({ ok: true, json: async () => ({ shows: [{ title: 'First' }] }) });
    await first;
    assert.equal(stash.shows[0].title, 'Second');
    stash.destroy();
});

test('feed requests use episode metadata endpoint and expose server errors', async () => {
    let requestUrl;
    const { stash } = setup({ fetcher: async url => {
        requestUrl = url;
        return { ok: false, json: async () => ({ error: 'This feed is not public.' }) };
    } });
    stash.episodesUrl = '/library/podcasts/episodes/';
    stash.query = 'https://podcasts.example/rss';
    await stash.search();
    assert.equal(new URL(requestUrl, 'https://cosound.example').searchParams.get('feed'), stash.query);
    assert.equal(stash.panel, 'episodes');
    assert.equal(stash.searchError, 'This feed is not public.');
    assert.equal(stash.busy, false);
    stash.destroy();
});

test('repeated submission shares the in-flight metadata request', async () => {
    let resolve;
    let count = 0;
    const { stash } = setup({ fetcher: () => {
        count++;
        return new Promise(done => { resolve = done; });
    } });
    stash.query = 'science';
    stash.queryChanged();
    const first = stash.search();
    await stash.search();
    assert.equal(count, 1);
    resolve({ ok: true, json: async () => ({ shows: [{ title: 'Science' }] }) });
    await first;
    assert.equal(stash.shows[0].title, 'Science');
    stash.destroy();
});

test('destroy aborts outstanding metadata and ignores its late result', async () => {
    let resolve, signal;
    const { stash } = setup({ fetcher: (_url, options) => {
        signal = options.signal;
        return new Promise(done => { resolve = done; });
    } });
    stash.query = 'science'; const result = stash.search();
    stash.destroy();
    assert.equal(signal.aborted, true);
    resolve({ ok: true, json: async () => ({ shows: [{ title: 'Late' }] }) });
    await result;
    assert.equal(stash.shows.length, 0);
});

test('duration formatting supports long episodes', () => {
    assert.equal(formatPodcastTime(3661), '1:01:01');
    assert.equal(formatPodcastTime(61), '1:01');
    assert.equal(formatPodcastTime(null), '0:00');
});
