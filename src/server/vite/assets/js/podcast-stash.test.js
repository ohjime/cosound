import test from 'node:test';
import assert from 'node:assert/strict';
import { createPodcastStash, formatPodcastTime, MAX_PODCASTS } from './podcast-stash.js';

const episode = index => ({ id: String(index), title: `Episode ${index}`, audio_url: `https://podcasts.example/${index}.mp3` });
function setup(options = {}) {
    let callbacks;
    const calls = [];
    const player = {
        load(item, settings) { calls.push(['load', item, settings]); return Promise.resolve(true); },
        play() { calls.push(['play']); }, pause() { calls.push(['pause']); },
        setVolume(value) { calls.push(['volume', value]); },
        setPreset(value) { calls.push(['preset', value]); },
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
    assert.equal(calls.length, 1);
    await stash.playAt(1);
    assert.deepEqual(calls.at(-1)[2], { autoplay: true, volume: .25, preset: 'vintage' });
    stash.setVolume(.5); stash.setPreset('radio');
    assert.deepEqual(calls.slice(-2), [['volume', .5], ['preset', 'radio']]);
    stash.destroy();
});

test('reordering keeps active and selected episodes stable and changes what follows', async () => {
    const { stash, calls, callbacks } = setup();
    [1, 2, 3].forEach(index => stash.add(episode(index)));
    await stash.playAt(0);
    stash.select(2); stash.move(2, -1);
    assert.equal(stash.activeIndex, 0);
    assert.equal(stash.selected.id, '3');
    callbacks.onEnded();
    assert.equal(calls.at(-1)[1].id, '3');
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
    assert.equal(calls.length, beforeClose, 'closing the presentation does not touch media');
    callbacks.onEnded();
    assert.equal(stash.activeIndex, 1);
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
