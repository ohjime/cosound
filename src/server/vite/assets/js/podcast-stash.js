import { PodcastPlayer } from './podcast-player.js';

export const MAX_PODCASTS = 12;

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
        status: { playing: false, loading: false, currentTime: 0, duration: 0, effectsAvailable: true, notice: '', error: '' },
        get selected() { return this.queue[this.selectedIndex] ?? null; },
        get activeIndex() { return this.queue.findIndex(item => item.key === this.activeId); },
        get full() { return this.queue.length >= MAX_PODCASTS; },
        get isSelectedActive() { return Boolean(this.selected && this.selected.key === this.activeId); },
        get isFeedQuery() { return /^https?:\/\//i.test(this.query.trim()); },
        formatTime: formatPodcastTime,
        formatDate(value) {
            const date = new Date(value);
            return value && Number.isFinite(date.getTime())
                ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '';
        },
        init() {
            this.searchUrl = this.$el?.dataset.searchUrl ?? this.searchUrl;
            this.episodesUrl = this.$el?.dataset.episodesUrl ?? this.episodesUrl;
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
                if (removed && (removed === this.$el || removed.contains?.(this.$el))) this.destroy();
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
            this.open = !this.open;
            if (this.open && !this.queue.length) this.panel = 'search';
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
            const item = { ...episode, key: `podcast-${++sequence}`, volume: 0.75, preset: 'clean' };
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
            await player.load(item, { volume: item.volume, preset: item.preset, autoplay: true });
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
            if (!this.selected || !['clean', 'radio', 'vintage', 'muffled'].includes(value)) return;
            this.selected.preset = value;
            if (this.isSelectedActive) player.setPreset(value);
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
