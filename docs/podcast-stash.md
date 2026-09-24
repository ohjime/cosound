# Podcast Stash

The Library has a **Podcast Stash** button below the soundscape card. It opens
a brown card that plays alongside the existing CoSound player, with its own
transport and volume. Explore and venue players have no podcast controls.

Search for a show or topic, or paste a public RSS/Atom feed URL and press Go.
Open a show and add episodes. The first episode stays selected as the queue
grows; press Play podcast to start. Episodes run one at a time in queue order,
and stop at the end. The numbered indicator selects an episode for inspection;
pressing Play starts that selection. The Queue tab can reorder and remove
episodes. The current limit is 12 episodes, and feeds expose up to 50 playable
entries in publisher order.

Each episode has its own volume and settings button, available to all Library
visitors. Effects are Original, Radio show (a narrow frequency range), Old-time
(a narrower range with gentle saturation), and Next room (a low-pass filter).
These settings follow their episode through queue reordering.

Collapsing the drawer keeps playback running. Leaving Library or refreshing
destroys its audio and clears the queue. There are no favourites, save controls,
database models, migrations, localStorage, or sessionStorage for podcasts.
Saving a CoSound still saves only its original sound layers.

## Data and cost

Apple's public iTunes Search API supplies discovery, without API credentials or
a paid provider dependency. The browser debounces searches and calls
`GET /library/podcasts/search/?q=…`. The response contains show metadata and feed
URLs. `GET /library/podcasts/episodes/?feed=…` fetches and normalizes RSS or Atom
metadata. Feed text is never inserted as HTML.

**CoSound does handle small metadata requests; this is not literally zero
server load.** Feed origins do not consistently allow browser cross-origin
requests, so a server metadata bridge makes discovery work across publishers.
The gateway never requests episode enclosures or artwork. Those URLs go to the
browser, which streams audio directly from the publisher using one ordinary
media element. Adding queue entries does not preload episode audio, and no
episode is decoded in full or recorded. Browsers may buffer active streams in
their normal media cache.

To bound prototype traffic, each server process has:

- A 4 MiB / 128-entry in-memory metadata cache: 15-minute search and 10-minute
  feed expiry. No database or disk cache is used.
- At most 4 simultaneous outbound requests; in-flight duplicates fail quickly.
- 20 uncached directory searches and 40 feed fetches per minute, plus 60
  metadata requests per minute per observed client address.
- 1 MiB search / 8 MiB feed response caps, 50 returned episodes, 3 redirects,
  a 10-second total network deadline, and bounded DNS work.
- Only public HTTP(S) addresses on standard ports. Every redirect is checked;
  sockets connect to verified public IPs while TLS verifies the original host.
  Private/local addresses, credentials, XML entities/DTDs, excessive nesting,
  compressed responses, and media content types are rejected.

These budgets and caches are **per process**, not shared across workers. A
reverse proxy may also collapse client addresses for the conservative client
limit. Before a larger release, coordinate the directory budget at the edge or
in a shared limiter. Apple's documented approximately 20 requests/minute is
subject to change and can be shared by workers behind one public IP. Limits,
timeouts, and publisher outages produce a visible retryable error, not a media
proxy fallback.

## Browser restrictions

Web Audio requires permission from the media host (CORS). The player first
attempts anonymous CORS streaming with its browser audio graph. When that path
fails, it replaces the element with a clean direct stream, retaining volume and
position where supported, and marks effects unavailable for that episode.
Failure of the ordinary stream is shown separately. No media proxy is used to
work around publisher restrictions. HTTP-only episodes cannot play from a
secure HTTPS page. Some hosts also reject external playback or links expire.

Autoplay restrictions can require another press of Play, including when moving
between episodes. The UI reports that state. Metadata alone cannot guarantee
that an enclosure is reachable or that a browser supports its audio format.

## Validation

From `src/server/vite`, `npm test` covers sequential playback, queue editing,
per-episode settings, search races, media fallbacks, filters, autoplay, stale
events, and cleanup. `npm run build` produces the frontend bundle.

From `src/server`, run `uv run python src/main.py test library.test_podcasts`.
These backend tests use no database and no live upstream network. They cover
RSS/Atom parsing, input validation, IP pinning, redirects, request bounds,
cache/limits, and endpoint responses. The templates must also pass the lexer
check in `src/server/AGENTS.md`.

Live smoke checks used Apple search and Radiolab's approximately 5 MiB public
feed. Publishers and browsers can change their responses independently of this
branch, so direct playback and fallback are also exercised in the local browser.

## Sources

- [Apple Search API parameters and limits](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/Searching.html)
- [RSS specification and episode enclosures](https://www.rssboard.org/rss-specification)
- [Web Audio media-element security restrictions](https://www.w3.org/TR/webaudio/#MediaElementAudioSourceNode-security)
- [Browser CORS rules](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [Podcast Index API](https://podcastindex-org.github.io/docs-api/): an alternative
  directory with API-key setup if the prototype later needs a different provider.
