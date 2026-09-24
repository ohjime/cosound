"""Small, read-only podcast directory/RSS gateway. Audio never passes through us.

Only normalized metadata lives in a bounded, short-lived process-memory cache.
All RSS connections use a verified public IP, including redirects, while HTTPS
still verifies the certificate for the original hostname. No proxy environment
variables, cookies, credentials, database records, or downloaded media are used.
"""

from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import threading
import time
from urllib.parse import quote, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

from django.http import JsonResponse
from django.views.decorators.http import require_GET


MAX_BODY = 8 * 1024 * 1024
MAX_SEARCH_BODY = 1024 * 1024
MAX_EPISODES = 50
MAX_SHOWS = 25
MAX_REDIRECTS = 3
REQUEST_TIMEOUT = 10
DNS_TIMEOUT = 3
CACHE_BYTES = 4 * 1024 * 1024
CACHE_ENTRIES = 128
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
ATOM = "{http://www.w3.org/2005/Atom}"
DC = "{http://purl.org/dc/elements/1.1/}"

_lock = threading.Lock()
_cache = OrderedDict()
_cache_size = 0
_clients = OrderedDict()
_budgets = {"search": deque(), "feed": deque()}
_network_slots = threading.BoundedSemaphore(4)
_dns_slots = threading.BoundedSemaphore(4)
_dns_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="podcast-dns")
_inflight = set()


class PodcastError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def _public_ip(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if not ip.is_global or ip.is_multicast:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped or ip.sixtofour or ip.teredo:
            return False
    return True


def _url(value):
    """Validate syntax without DNS (also used for creator-hosted media links)."""
    if not isinstance(value, str) or len(value) > 2048:
        raise PodcastError("Enter a valid public RSS feed URL.", 400)
    if re.search(r"[\s\x00-\x1f\x7f\\]", value):
        raise PodcastError("Enter a valid public RSS feed URL.", 400)
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").encode("idna").decode("ascii").lower()
        port = parts.port
        if (
            parts.scheme not in ("http", "https")
            or not host
            or parts.username is not None
            or parts.password is not None
            or parts.fragment
            or (port is not None and port != (443 if parts.scheme == "https" else 80))
            or "%" in host
        ):
            raise ValueError
        host = host.rstrip(".")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if "." not in host or host.endswith((".localhost", ".local", ".internal", ".invalid", ".test")):
                raise ValueError
            if not re.fullmatch(r"[a-z0-9.-]+", host):
                raise ValueError
        else:
            if not _public_ip(host):
                raise ValueError
    except (ValueError, UnicodeError):
        raise PodcastError("Only public HTTP or HTTPS feed URLs are supported.", 400) from None
    netloc = f"[{host}]" if ":" in host else host
    path = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="%=&;:+,/?@!$'()*-._~")
    return urlunsplit((parts.scheme, netloc, path, query, ""))


def _resolve(host, port, timeout):
    if not _dns_slots.acquire(blocking=False):
        raise PodcastError("Podcast lookup is busy. Please try again shortly.", 503)
    future = _dns_executor.submit(
        socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM, socket.IPPROTO_TCP
    )
    future.add_done_callback(lambda _: _dns_slots.release())
    try:
        records = future.result(timeout=min(DNS_TIMEOUT, timeout))
    except (FutureTimeout, OSError):
        raise PodcastError("That podcast host could not be reached.") from None
    addresses = list(dict.fromkeys((family, sockaddr[0]) for family, _, _, _, sockaddr in records))
    if not addresses or any(not _public_ip(address) for _, address in addresses):
        raise PodcastError("Only public podcast hosts are supported.", 400)
    # Prefer IPv4 when both exist; some hosts advertise AAAA records while the
    # deployment itself has no IPv6 route. Both families still undergo checks.
    return sorted(addresses, key=lambda record: record[0] != socket.AF_INET)


class _PinnedConnection(http.client.HTTPConnection):
    def __init__(self, host, port, address, *, secure, timeout):
        super().__init__(host, port, timeout=timeout)
        self.address = address
        self.secure = secure
        self.transport = None
        self.deadline = time.monotonic() + timeout
        self.expired = threading.Event()

    def abort(self):
        self.expired.set()
        if self.transport is not None:
            try:
                self.transport.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.transport.close()

    def connect(self):
        family, address = self.address
        sock = socket.socket(family, socket.SOCK_STREAM)
        self.transport = sock
        try:
            if self.expired.is_set():
                raise TimeoutError
            sock.settimeout(self.timeout)
            sock.connect((address, self.port))
            if self.secure:
                sock.settimeout(max(0.01, self.deadline - time.monotonic()))
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=self.host)
                self.transport = sock
            if self.expired.is_set():
                raise TimeoutError
            self.sock = sock
        except Exception:
            sock.close()
            raise


def _download(value, *, limit=MAX_BODY, accept="application/rss+xml, application/atom+xml, application/xml, text/xml"):
    deadline = time.monotonic() + REQUEST_TIMEOUT
    current = _url(value)
    for redirect in range(MAX_REDIRECTS + 1):
        parts = urlsplit(current)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PodcastError("That podcast host took too long to respond.")
        port = 443 if parts.scheme == "https" else 80
        addresses = _resolve(parts.hostname, port, remaining)
        connection = _PinnedConnection(
            parts.hostname, port, addresses[0], secure=parts.scheme == "https",
            timeout=max(0.1, deadline - time.monotonic()),
        )
        # A socket timeout alone does not stop a peer trickling response headers.
        # The watchdog interrupts the actual pinned socket at the total deadline.
        watchdog = threading.Timer(max(0.01, deadline - time.monotonic()), connection.abort)
        watchdog.daemon = True
        watchdog.start()
        response = None
        try:
            target = urlunsplit(("", "", parts.path, parts.query, ""))
            connection.request("GET", target, headers={
                "Accept": accept,
                "Accept-Encoding": "identity",
                "User-Agent": "CoSound-PodcastStash/1.0 (RSS metadata only)",
                "Connection": "close",
            })
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location or redirect == MAX_REDIRECTS:
                    raise PodcastError("That feed redirected too many times.")
                current = _url(urljoin(current, location))
                continue
            if response.status != 200:
                raise PodcastError("The podcast provider could not return this feed.")
            content_type = response.getheader("Content-Type", "").lower().split(";", 1)[0]
            if content_type.startswith(("audio/", "video/", "image/")):
                raise PodcastError("Enter the podcast's RSS feed, rather than a media file.")
            encoding = response.getheader("Content-Encoding", "identity").lower()
            if encoding not in ("", "identity"):
                raise PodcastError("That provider returned an unsupported compressed feed.")
            length = response.getheader("Content-Length")
            if length:
                try:
                    if int(length) < 0 or int(length) > limit:
                        raise PodcastError("That podcast feed is too large to browse.")
                except ValueError:
                    raise PodcastError("That provider returned an invalid feed.") from None
            body = bytearray()
            while len(body) <= limit:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PodcastError("That podcast host took too long to respond.")
                # read1 performs at most one buffered socket read, allowing the
                # total deadline to be checked even against a slow-drip host.
                if connection.transport and connection.transport.fileno() != -1:
                    connection.transport.settimeout(remaining)
                chunk = response.read1(min(65536, limit + 1 - len(body)))
                if not chunk:
                    return bytes(body), current
                body.extend(chunk)
            raise PodcastError("That podcast feed is too large to browse.")
        except (OSError, http.client.HTTPException, UnicodeError):
            raise PodcastError("That podcast host could not be reached. Try another feed.") from None
        finally:
            watchdog.cancel()
            if response is not None:
                response.close()
            connection.close()
    raise PodcastError("That feed redirected too many times.")


def _text(node, *names, default="", limit=300):
    for name in names:
        element = node.find(name)
        if element is not None:
            value = " ".join("".join(element.itertext()).split())
            if value:
                return value[:limit]
    return default


def _media_url(value, base):
    if not isinstance(value, str):
        return ""
    try:
        return _url(urljoin(base, (value or "").strip())) if value else ""
    except PodcastError:
        return ""


def _artwork(node, base, fallback=""):
    image = node.find(f"{ITUNES}image")
    if image is not None:
        url = _media_url(image.get("href"), base)
        if url:
            return url
    return _media_url(_text(node, "image/url", f"{ATOM}logo", f"{ATOM}icon", limit=2048), base) or fallback


def _duration(value):
    try:
        pieces = value.strip().split(":")
        if not 1 <= len(pieces) <= 3 or any(not re.fullmatch(r"\d+(?:\.\d+)?", piece) for piece in pieces):
            return None
        seconds = 0
        for piece in pieces:
            seconds = seconds * 60 + float(piece)
        return int(seconds) if 0 <= seconds <= 30 * 24 * 3600 else None
    except (ValueError, OverflowError):
        return None


def _published(value):
    try:
        date = parsedate_to_datetime(value)
    except (ValueError, TypeError, OverflowError):
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return ""
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    try:
        return date.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return ""


def _parse_feed(body, feed_url):
    if len(body) > MAX_BODY:
        raise PodcastError("That podcast feed is too large to browse.")
    if b"\x00" in body or re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", body, re.I):
        raise PodcastError("That feed uses unsupported XML declarations.")
    parser = ET.XMLPullParser(events=("start", "end"))
    root = None
    nodes = depth = 0
    try:
        for offset in range(0, len(body), 65536):
            parser.feed(body[offset:offset + 65536])
            for event, element in parser.read_events():
                if event == "start":
                    root = element if root is None else root
                    nodes += 1
                    depth += 1
                    if nodes > 60000 or depth > 32:
                        raise PodcastError("That podcast feed is too complex to browse.")
                else:
                    depth -= 1
        parser.close()
    except (ET.ParseError, ValueError):
        raise PodcastError("That URL did not return a valid RSS or Atom feed.") from None
    channel = root.find("channel") if root is not None and root.tag == "rss" else root
    atom = channel is not None and channel.tag == f"{ATOM}feed"
    if channel is None or (channel.tag != "channel" and not atom):
        raise PodcastError("That URL did not return a podcast RSS or Atom feed.")
    show = {
        "title": _text(channel, "title", f"{ATOM}title", default="Untitled podcast"),
        "author": _text(channel, f"{ITUNES}author", f"{DC}creator", f"{ATOM}author/{ATOM}name", "managingEditor", limit=200),
        "artwork": _artwork(channel, feed_url),
        "feed_url": feed_url,
    }
    episodes = []
    seen = set()
    for item in channel.findall(f"{ATOM}entry" if atom else "item"):
        audio_url = ""
        for enclosure in item.findall(f"{ATOM}link" if atom else "enclosure"):
            if atom and enclosure.get("rel") != "enclosure":
                continue
            media_type = enclosure.get("type", "").lower().split(";", 1)[0].strip()
            url = _media_url(enclosure.get("href" if atom else "url"), feed_url)
            extension = urlsplit(url).path.lower().rsplit(".", 1)[-1]
            if url and (media_type.startswith("audio/") or media_type == "application/ogg" or (not media_type and extension in {"mp3", "m4a", "aac", "ogg", "opus", "wav", "flac", "webm"})):
                audio_url = url
                break
        if not audio_url or audio_url in seen:
            continue
        seen.add(audio_url)
        identity = _text(item, "guid", f"{ATOM}id", default=audio_url, limit=2048)
        episodes.append({
            "id": hashlib.sha256((feed_url + "\n" + identity).encode()).hexdigest()[:24],
            "title": _text(item, "title", f"{ATOM}title", default="Untitled episode"),
            "author": _text(item, f"{ITUNES}author", f"{DC}creator", f"{ATOM}author/{ATOM}name", default=show["author"], limit=200),
            "show_title": show["title"],
            "artwork": _artwork(item, feed_url, show["artwork"]),
            "audio_url": audio_url,
            "duration": _duration(_text(item, f"{ITUNES}duration")),
            "published": _published(_text(item, "pubDate", f"{ATOM}published", f"{ATOM}updated")),
        })
        if len(episodes) >= MAX_EPISODES:
            break
    return {"show": show, "episodes": episodes}


def _search(query):
    body, _ = _download(
        "https://itunes.apple.com/search?" + urlencode({"term": query, "media": "podcast", "entity": "podcast", "limit": MAX_SHOWS}),
        limit=MAX_SEARCH_BODY, accept="application/json",
    )
    try:
        payload = json.loads(body)
        results = payload.get("results")
        if not isinstance(results, list):
            raise ValueError
    except (ValueError, AttributeError, UnicodeError):
        raise PodcastError("Podcast search is temporarily unavailable.") from None
    shows = []
    seen = set()
    for result in results[:100]:
        if not isinstance(result, dict):
            continue
        feed = _media_url(result.get("feedUrl"), "")
        if not feed or feed in seen:
            continue
        seen.add(feed)
        shows.append({
            "id": str(result.get("collectionId") or hashlib.sha256(feed.encode()).hexdigest()[:24])[:100],
            "title": str(result.get("collectionName") or result.get("trackName") or "Untitled podcast")[:300],
            "author": str(result.get("artistName") or "")[:200],
            "artwork": _media_url(result.get("artworkUrl600") or result.get("artworkUrl100"), ""),
            "feed_url": feed,
        })
        if len(shows) >= MAX_SHOWS:
            break
    return {"shows": shows}


def _consume(events, limit, now):
    while events and events[0] <= now - 60:
        events.popleft()
    if len(events) >= limit:
        raise PodcastError("Podcast lookup limit reached. Please try again in a minute.", 429)
    events.append(now)


def _client_limit(request):
    # REMOTE_ADDR is server-provided; forwarded headers are deliberately ignored.
    identity = str(request.META.get("REMOTE_ADDR", "unknown"))[:100]
    now = time.monotonic()
    with _lock:
        events = _clients.pop(identity, deque())
        _clients[identity] = events
        while len(_clients) > 1024:
            _clients.popitem(last=False)
        _consume(events, 60, now)


def _cached(kind, key, loader):
    global _cache_size
    cache_key = (kind, key)
    now = time.monotonic()
    with _lock:
        for old_key, (expires, _, size) in list(_cache.items()):
            if expires <= now:
                del _cache[old_key]
                _cache_size -= size
        entry = _cache.get(cache_key)
        if entry:
            _cache.move_to_end(cache_key)
            return entry[1]
        if cache_key in _inflight or not _network_slots.acquire(blocking=False):
            raise PodcastError("Podcast lookup is busy. Please try again shortly.", 503)
        try:
            _consume(_budgets[kind], 20 if kind == "search" else 40, now)
        except PodcastError:
            _network_slots.release()
            raise
        _inflight.add(cache_key)
    try:
        payload = loader()
        size = len(json.dumps(payload).encode())
        with _lock:
            if size <= CACHE_BYTES:
                while _cache and (len(_cache) >= CACHE_ENTRIES or _cache_size + size > CACHE_BYTES):
                    _, (_, _, removed_size) = _cache.popitem(last=False)
                    _cache_size -= removed_size
                _cache[cache_key] = (time.monotonic() + (900 if kind == "search" else 600), payload, size)
                _cache_size += size
        return payload
    finally:
        with _lock:
            _inflight.discard(cache_key)
        _network_slots.release()


def _response(request, loader):
    try:
        _client_limit(request)
        response = JsonResponse(loader())
    except PodcastError as error:
        response = JsonResponse({"error": str(error)}, status=error.status)
        if error.status in (429, 503):
            response["Retry-After"] = "60" if error.status == 429 else "3"
    response["Cache-Control"] = "no-store"
    return response


@require_GET
def podcast_search(request):
    def load():
        query = " ".join(request.GET.get("q", "").split())
        if not 2 <= len(query) <= 120:
            raise PodcastError("Search using between 2 and 120 characters.", 400)
        return _cached("search", query.casefold(), lambda: _search(query))
    return _response(request, load)


@require_GET
def podcast_episodes(request):
    def load():
        feed = _url(request.GET.get("feed", ""))
        def fetch():
            body, final_url = _download(feed)
            return _parse_feed(body, final_url)
        return _cached("feed", feed, fetch)
    return _response(request, load)
