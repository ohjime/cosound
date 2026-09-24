import { PodcastPlayer } from './podcast-player.js';
import { DEFAULT_PODCAST_EFFECTS, getPodcastPreset, PODCAST_PRESETS } from './podcast-effects.js';

export const MAX_PODCASTS = 12;

function clampEffect(value, fallback) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(0, Math.min(1, number)) : fallback;
}

export function formatPodcastTime(value) {
    const seconds = Math.max(0, Math.floor(Number(value) || 0));
    const minutes = Math.floor(seconds / 60);
    return minutes >= 60
        ? `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`
        : `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
}

// Native media and request objects stay in this closure, outside Alpine's
// reactive proxy. Nothing is persisted or handed to the soundscape save path.
export function createPodcastStash({ playerFactory, fetcher, eventTarget } = {}) {
    let player;
    let request;
    let requestVersion = 0;
    let requestKey = '';
    let searchTimer;
    let sequence = 0;
    let disposed = false;
    let cleanup;
    let root;
    const events = eventTarget ?? globalThis.document;
    const fetchMetadata = fetcher ?? ((...args) => fetch(...args));
    return {
        open: false,
        panel: 'search',
        query: '',
        searchUrl: '',
        episodesUrl: '',
        shows: [],
        episodes: [],
        show: null,
        searched: false,
        busy: false,
        searchError: '',
        queueMessage: '',
        queue: [],
        selectedIndex: 0,
        activeId: null,
        settingsOpen: false,
        presets: PODCAST_PRESETS,
        status: { playing: false, loading: false, currentTime: 0, duration: 0, effectsAvailable: true, notice: '', error: '' },
        get selected() { return this.queue[this.selectedIndex] ?? null; },
        get selectedPreset() { return getPodcastPreset(this.selected?.preset ?? 'clean'); },
        get activeIndex() { return this.queue.findIndex(item => item.key === this.activeId); },
        get full() { return this.queue.length >= MAX_PODCASTS; },
        get isSelectedActive() { return Boolean(this.selected && this.selected.key === this.activeId); },
        get effectsBlocked() { return this.isSelectedActive && this.status.effectsAvailable === false; },
        get isFeedQuery() { return /^https?:\/\//i.test(this.query.trim()); },
        formatTime: formatPodcastTime,
        formatDate(value) {
            const date = new Date(value);
            return value && Number.isFinite(date.getTime())
                ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';
        },
        init() {
            root = this.$el;
            this.searchUrl = root?.dataset?.searchUrl ?? this.searchUrl;
            this.episodesUrl = root?.dataset?.episodesUrl ?? this.episodesUrl;
            player = (playerFactory ?? (options => new PodcastPlayer(options)))({
                onChange: status => { if (!disposed) this.status = { ...this.status, ...status }; },
                onEnded: () => {
                    if (disposed) return;
                    const next = this.activeIndex + 1;
                    if (next > 0 && next < this.queue.length) this.playAt(next);
                },
            });
            cleanup = event => {
                const removed = event.detail?.elt;
                if (removed && (removed === root || removed.contains?.(root))) this.destroy();
            };
            events?.addEventListener('htmx:beforeCleanupElement', cleanup);
        },
        destroy() {
            if (disposed) return;
            disposed = true;
            requestVersion++;
            request?.abort();
            clearTimeout(searchTimer);
            events?.removeEventListener('htmx:beforeCleanupElement', cleanup);
            player?.destroy();
        },
        toggleDrawer() {
            if (disposed) return;
            this.open = !this.open;
            if (this.open && !this.queue.length) this.panel = 'search';
            if (this.open) this.$nextTick?.(() => {
                const card = root?.querySelector('#podcast-drawer');
                card?.querySelector('.podcast-card')?.focus({ preventScroll: true });
                root?.querySelector('#deck')?.scrollIntoView({ block: 'start', behavior: 'instant' });
            });
        },
        cardRemoved(card) {
            // The deck can dismiss us when another overlay opens. An old
            // animation finishing after a reopen must not hide the new card.
            if (card?.dataset.cardKey === 'library-podcasts'
                && !root?.querySelector('#podcast-drawer')) this.open = false;
        },
        async metadata(url, params, accept) {
            if (disposed) return;
            const key = `${url}?${new URLSearchParams(params)}`;
            if (this.busy && requestKey === key) return;
            requestKey = key;
            request?.abort();
            const version = ++requestVersion;
            request = new AbortController();
            const controller = request;
            this.busy = true;
            this.searchError = '';
            const timeout = setTimeout(() => controller.abort(), 20000);
            try {
                const response = await fetchMetadata(key, {
                    signal: controller.signal,
                    headers: { Accept: 'application/json' },
                    credentials: 'same-origin',
                });
                const data = await response.json();
                if (disposed || version !== requestVersion) return;
                if (!response.ok) throw new Error(data.error || 'Podcasts could not be loaded. Please try again.');
                accept(data);
            } catch (error) {
                if (!disposed && version === requestVersion) {
                    this.searchError = error.name === 'AbortError'
                        ? 'The podcast service took too long. Please try again.'
                        : error.message || 'Check your connection and try again.';
                }
            } finally {
                clearTimeout(timeout);
                if (!disposed && version === requestVersion) this.busy = false;
            }
        },
        queryChanged() {
            if (disposed) return;
            // Invalidate the old response immediately, before the debounce.
            request?.abort();
            requestVersion++;
            this.busy = false;
            this.searchError = '';
            this.shows = [];
            this.searched = false;
            clearTimeout(searchTimer);
            if (!this.isFeedQuery && this.query.trim().length >= 2) {
                searchTimer = setTimeout(() => { if (!disposed) this.search(); }, 500);
            }
        },
        async search() {
            if (disposed) return;
            clearTimeout(searchTimer);
            const query = this.query.trim();
            this.panel = 'search';
            if (this.isFeedQuery) return this.browse({ feed_url: query });
            if (query.length < 2) return;
            this.shows = [];
            this.searched = false;
            await this.metadata(this.searchUrl, { q: query }, data => {
                this.shows = data.shows ?? [];
                this.searched = true;
            });
        },
        async browse(show) {
            if (disposed) return;
            clearTimeout(searchTimer);
            this.show = show;
            this.episodes = [];
            this.panel = 'episodes';
            await this.metadata(this.episodesUrl, { feed: show.feed_url }, data => {
                this.show = { ...show, ...data.show };
                this.episodes = data.episodes ?? [];
            });
        },
        backToSearch() {
            clearTimeout(searchTimer);
            request?.abort();
            requestVersion++;
            this.busy = false;
            this.searchError = '';
            this.panel = 'search';
        },
        queued(episode) { return this.queue.some(item => item.audio_url === episode.audio_url); },
        add(episode) {
            if (this.full || this.queued(episode)) return;
            const item = {
                ...episode, key: `podcast-${++sequence}`, volume: 0.75,
                preset: 'clean', ...DEFAULT_PODCAST_EFFECTS,
            };
            this.queue.push(item);
            if (this.queue.length === 1) this.selectedIndex = 0;
            this.queueMessage = `Added ${episode.title}. ${this.queue.length} in your queue.`;
        },
        select(index) {
            if (!this.queue[index]) return;
            this.selectedIndex = index;
            this.settingsOpen = false;
        },
        async playAt(index) {
            const item = this.queue[index];
            if (!item || disposed) return;
            this.selectedIndex = index;
            this.activeId = item.key;
            await player.load(item, {
                volume: item.volume, preset: item.preset,
                effectMix: item.effectMix, texture: item.texture, space: item.space,
                autoplay: true,
            });
        },
        async togglePlayback() {
            if (!this.selected) return;
            if (!this.isSelectedActive || this.status.error) return this.playAt(this.selectedIndex);
            if (this.status.playing || this.status.loading) player.pause();
            else await player.play();
        },
        next() {
            const next = this.activeIndex + 1;
            if (next < this.queue.length) return this.playAt(next);
        },
        seek(value) { player.seek(Number(value)); },
        setVolume(value) {
            if (!this.selected) return;
            this.selected.volume = Math.max(0, Math.min(1, Number(value) || 0));
            if (this.isSelectedActive) player.setVolume(this.selected.volume);
        },
        setPreset(value) {
            if (disposed || !this.selected || !PODCAST_PRESETS.some(preset => preset.id === value)) return;
            this.selected.preset = value;
            if (this.isSelectedActive) player.setPreset(value);
        },
        setEffectMix(value) {
            if (disposed || !this.selected) return;
            this.selected.effectMix = clampEffect(value, this.selected.effectMix);
            if (this.isSelectedActive) player.setEffectMix(this.selected.effectMix);
        },
        setTexture(value) {
            if (disposed || !this.selected) return;
            this.selected.texture = clampEffect(value, this.selected.texture);
            if (this.isSelectedActive) player.setTexture(this.selected.texture);
        },
        setSpace(value) {
            if (disposed || !this.selected) return;
            this.selected.space = clampEffect(value, this.selected.space);
            if (this.isSelectedActive) player.setSpace(this.selected.space);
        },
        resetEffects() {
            if (disposed || !this.selected) return;
            // Update the existing graph in the same turn, preserving the
            // listener's playback position and each other episode's settings.
            this.setPreset('clean');
            this.setEffectMix(DEFAULT_PODCAST_EFFECTS.effectMix);
            this.setTexture(DEFAULT_PODCAST_EFFECTS.texture);
            this.setSpace(DEFAULT_PODCAST_EFFECTS.space);
        },
        async auditionPreset(value) {
            if (disposed || !this.selected || !PODCAST_PRESETS.some(preset => preset.id === value)) return;
            this.setPreset(value);
            if (!this.isSelectedActive || this.status.error) return this.playAt(this.selectedIndex);
            if (!this.status.playing && !this.status.loading) await player.play();
        },
        move(index, offset) {
            const target = index + offset;
            if (target < 0 || target >= this.queue.length) return;
            const selectedKey = this.selected?.key;
            [this.queue[index], this.queue[target]] = [this.queue[target], this.queue[index]];
            this.selectedIndex = this.queue.findIndex(item => item.key === selectedKey);
        },
        remove(index) {
            const removed = this.queue[index];
            if (!removed) return;
            const selectedKey = this.selected?.key;
            const wasActive = removed.key === this.activeId;
            const wasPlaying = this.status.playing || this.status.loading;
            if (wasActive) player.pause();
            this.queue.splice(index, 1);
            const selection = this.queue.findIndex(item => item.key === selectedKey);
            this.selectedIndex = selection >= 0 ? selection : Math.min(index, Math.max(0, this.queue.length - 1));
            if (wasActive) {
                this.activeId = null;
                this.status = { ...this.status, playing: false, loading: false, currentTime: 0, duration: 0, error: '', notice: '' };
                if (wasPlaying && this.queue[index]) this.playAt(index);
                // Clear the removed source even when paused: no background
                // download continues after the listener removes an episode.
                else player.load(null);
            }
            this.queueMessage = `Removed ${removed.title}.`;
        },
    };
}

export function podcastStash() { return createPodcastStash(); }
