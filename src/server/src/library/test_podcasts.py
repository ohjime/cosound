import io
import json
import socket
import threading
import time
from concurrent.futures import TimeoutError as FutureTimeout
from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import resolve, reverse

from library import podcasts as p


FEED_URL = "https://feeds.example.com/show.xml"
RSS = b'''<?xml version="1.0"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
 xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>Example &amp; Friends</title><itunes:author>The Host</itunes:author>
<itunes:image href="https://media.example.com/show.jpg"/>
<item><guid>episode-2</guid><title>Latest episode</title>
<itunes:duration>1:02:03</itunes:duration><pubDate>Mon, 21 Sep 2026 12:00:00 GMT</pubDate>
<enclosure url="https://media.example.com/2.mp3?token=abc&amp;x=1" type="audio/mpeg"/>
</item><item><title>Previous episode</title><dc:creator>Guest Host</dc:creator>
<itunes:image href="/episode.jpg"/><itunes:duration>90</itunes:duration>
<enclosure url="/1.m4a" type="audio/mp4"/></item>
<item><title>Not audio</title><enclosure url="/video.mp4" type="video/mp4"/></item>
</channel></rss>'''


class FakeResponse:
    def __init__(self, body=b"", status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self.body = io.BytesIO(body)
        self.closed = False

    def getheader(self, key, default=None):
        return self.headers.get(key, default)

    def read1(self, count):
        return self.body.read(count)

    def close(self):
        self.closed = True


class PodcastFeedTests(SimpleTestCase):
    def test_rss_namespaces_metadata_relative_links_and_feed_order(self):
        data = p._parse_feed(RSS, FEED_URL)
        self.assertEqual(data["show"]["title"], "Example & Friends")
        self.assertEqual(data["show"]["author"], "The Host")
        self.assertEqual(len(data["episodes"]), 2)
        first, second = data["episodes"]
        self.assertEqual(first["title"], "Latest episode")
        self.assertEqual(first["duration"], 3723)
        self.assertEqual(first["published"], "2026-09-21T12:00:00+00:00")
        self.assertEqual(first["audio_url"], "https://media.example.com/2.mp3?token=abc&x=1")
        self.assertEqual(first["artwork"], data["show"]["artwork"])
        self.assertEqual(second["author"], "Guest Host")
        self.assertEqual(second["artwork"], "https://feeds.example.com/episode.jpg")
        self.assertEqual(second["audio_url"], "https://feeds.example.com/1.m4a")
        self.assertEqual(set(first), {"id", "title", "author", "show_title", "artwork", "audio_url", "duration", "published"})

    def test_atom_audio_enclosures(self):
        body = b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom show</title>
        <author><name>Atom host</name></author><logo>https://media.example.com/logo.jpg</logo>
        <entry><id>a1</id><title>Episode</title><published>2026-09-20T10:00:00Z</published>
        <link rel="alternate" href="https://example.com/article"/>
        <link rel="enclosure" href="https://example.com/episode.ogg" type="audio/ogg"/>
        </entry></feed>'''
        data = p._parse_feed(body, FEED_URL)
        self.assertEqual(data["episodes"][0]["author"], "Atom host")
        self.assertEqual(data["episodes"][0]["published"], "2026-09-20T10:00:00+00:00")

    def test_invalid_feeds_and_xml_entities_are_rejected(self):
        for body in (
            b"<rss>", b"<html><body>Hello</body></html>", b"",
            b'<!DOCTYPE rss [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss><channel/></rss>',
            b'<!DOCTYPE rss [<!ENTITY x "huge">]><rss><channel><title>&x;</title></channel></rss>',
            '<rss><channel/></rss>'.encode("utf-16"),
            b"<rss><channel>" + b"<a>" * 40 + b"</a>" * 40 + b"</channel></rss>",
        ):
            with self.subTest(body=body[:50]), self.assertRaises(p.PodcastError):
                p._parse_feed(body, FEED_URL)

    def test_parser_size_limit(self):
        with patch.object(p, "MAX_BODY", 20), self.assertRaises(p.PodcastError):
            p._parse_feed(RSS, FEED_URL)

    def test_episode_limit_and_duplicates(self):
        items = "".join(f'<item><title>{i}</title><enclosure url="https://example.com/{i}.mp3" type="audio/mpeg"/></item>' for i in range(60))
        body = f"<rss><channel><title>Show</title>{items}{items}</channel></rss>".encode()
        data = p._parse_feed(body, FEED_URL)
        self.assertEqual(len(data["episodes"]), 50)
        self.assertEqual(data["episodes"][-1]["title"], "49")
        duplicate = b'<rss><channel><item><enclosure url="https://example.com/e.mp3"/></item><item><enclosure url="https://example.com/e.mp3"/></item></channel></rss>'
        self.assertEqual(len(p._parse_feed(duplicate, FEED_URL)["episodes"]), 1)

    def test_unsafe_media_and_non_audio_enclosures_are_omitted(self):
        body = b'''<rss><channel><itunes:image xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" href="http://127.0.0.1/pic"/>
        <item><enclosure url="http://169.254.169.254/audio.mp3" type="audio/mpeg"/></item>
        <item><enclosure url="javascript:alert(1)" type="audio/mpeg"/></item>
        <item><enclosure url="https://example.com/fake.mp3" type="text/html"/></item>
        </channel></rss>'''
        data = p._parse_feed(body, FEED_URL)
        self.assertEqual(data["episodes"], [])
        self.assertEqual(data["show"]["artwork"], "")

    def test_duration_and_date_failures_do_not_break_feed(self):
        for value in ("nope", "-1", "1:2:3:4", "inf", "9" * 500):
            self.assertIsNone(p._duration(value))
        self.assertEqual(p._duration("12.5"), 12)
        self.assertEqual(p._published("nonsense"), "")


class PodcastFetchSecurityTests(SimpleTestCase):
    def test_rejects_private_addresses_credentials_ports_and_schemes(self):
        for url in (
            "http://localhost/rss", "http://private.local/rss", "http://127.0.0.1/rss",
            "http://169.254.169.254/metadata", "http://10.0.0.1/rss", "http://100.64.0.1/rss",
            "https://[::1]/rss", "https://[::ffff:127.0.0.1]/rss", "https://[fe80::1%en0]/rss",
            "https://[2002:7f00:1::]/rss", "http://192.168.0.1/rss", "file:///etc/passwd",
            "ftp://example.com/rss", "https://user:password@example.com/rss",
            "https://example.com:8443/rss", "http://example.com:443/rss",
            "https://example.com/rss#secret", "https://example.com/\nheader", "https://example.com\\@127.0.0.1/rss",
        ):
            with self.subTest(url=url), self.assertRaises(p.PodcastError):
                p._url(url)

    def test_public_url_is_canonicalized(self):
        self.assertEqual(p._url("https://FEEDS.Example.COM:443/café"), "https://feeds.example.com/caf%C3%A9")

    def test_dns_rejects_any_private_resolution_including_mixed_answers(self):
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ("93.184.216.34", "127.0.0.1")]
        with patch.object(p.socket, "getaddrinfo", return_value=records):
            with self.assertRaises(p.PodcastError):
                p._resolve("feeds.example.com", 443, 1)

    def test_dns_timeout_and_saturation_are_bounded(self):
        future = MagicMock()
        future.result.side_effect = FutureTimeout
        with patch.object(p, "_dns_executor") as executor, patch.object(p, "_dns_slots") as slots:
            slots.acquire.return_value = True
            executor.submit.return_value = future
            with self.assertRaises(p.PodcastError):
                p._resolve("feeds.example.com", 443, 20)
            future.result.assert_called_once_with(timeout=p.DNS_TIMEOUT)
            slots.acquire.return_value = False
            with self.assertRaises(p.PodcastError) as caught:
                p._resolve("feeds.example.com", 443, 20)
            self.assertEqual(caught.exception.status, 503)

    def test_connection_pins_ip_and_verifies_tls_for_original_host(self):
        sock = MagicMock()
        tls = MagicMock()
        with patch.object(p.socket, "socket", return_value=sock), patch.object(p.ssl, "create_default_context", return_value=tls), patch.object(p.socket, "getaddrinfo") as dns:
            connection = p._PinnedConnection("feeds.example.com", 443, (socket.AF_INET, "93.184.216.34"), secure=True, timeout=3)
            connection.connect()
            sock.connect.assert_called_once_with(("93.184.216.34", 443))
            tls.wrap_socket.assert_called_once_with(sock, server_hostname="feeds.example.com")
            dns.assert_not_called()

    def download_with_responses(self, responses, **kwargs):
        connections = []
        for response in responses:
            connection = MagicMock()
            connection.getresponse.return_value = response
            connections.append(connection)
        with patch.object(p, "_resolve", return_value=[(socket.AF_INET, "93.184.216.34")]) as dns, patch.object(p, "_PinnedConnection", side_effect=connections):
            result = p._download(FEED_URL, **kwargs)
        return result, dns

    def test_redirects_resolve_each_destination_and_return_final_feed_url(self):
        redirect = FakeResponse(status=302, headers={"Location": "https://other.example.com/feed"})
        result, dns = self.download_with_responses([redirect, FakeResponse(RSS)])
        self.assertEqual(result, (RSS, "https://other.example.com/feed"))
        self.assertEqual([call.args[0] for call in dns.call_args_list], ["feeds.example.com", "other.example.com"])
        self.assertTrue(redirect.closed)

    def test_redirect_to_private_host_is_rejected_before_connecting(self):
        with self.assertRaises(p.PodcastError):
            self.download_with_responses([FakeResponse(status=302, headers={"Location": "http://127.0.0.1/private"})])

    def test_dns_rebinding_on_redirect_is_rejected(self):
        first = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        rebound = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        connection = MagicMock()
        connection.getresponse.return_value = FakeResponse(status=302, headers={"Location": "/second"})
        with patch.object(p.socket, "getaddrinfo", side_effect=[first, rebound]), patch.object(p, "_PinnedConnection", return_value=connection) as factory:
            with self.assertRaises(p.PodcastError):
                p._download(FEED_URL)
            self.assertEqual(factory.call_count, 1)

    def test_oversized_chunked_and_declared_bodies_are_rejected_and_closed(self):
        for response in (FakeResponse(b"x" * 31), FakeResponse(headers={"Content-Length": "31"})):
            with self.subTest(headers=response.headers), self.assertRaises(p.PodcastError):
                self.download_with_responses([response], limit=30)
            self.assertTrue(response.closed)

    def test_redirect_limit_provider_failure_and_compression(self):
        scenarios = [
            [FakeResponse(status=302, headers={"Location": "/again"}) for _ in range(4)],
            [FakeResponse(status=404)],
            [FakeResponse(headers={"Content-Encoding": "gzip"})],
            [FakeResponse(headers={"Content-Length": "not-a-number"})],
            [FakeResponse(headers={"Content-Type": "audio/mpeg"})],
        ]
        for responses in scenarios:
            with self.subTest(responses=responses), self.assertRaises(p.PodcastError):
                self.download_with_responses(responses)

    def test_complete_http_response_handles_socket_closed_at_content_length(self):
        client, server = socket.socketpair()
        connection = p._PinnedConnection("feeds.example.com", 80, (socket.AF_INET, "93.184.216.34"), secure=False, timeout=1)
        connection.sock = connection.transport = client
        server.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello")
        try:
            with patch.object(p, "_resolve", return_value=[(socket.AF_INET, "93.184.216.34")]), patch.object(p, "_PinnedConnection", return_value=connection):
                body, _ = p._download("http://feeds.example.com/rss")
            self.assertEqual(body, b"hello")
        finally:
            client.close()
            server.close()

    def test_total_deadline_stops_trickled_response_headers(self):
        client, server = socket.socketpair()
        connection = p._PinnedConnection("feeds.example.com", 80, (socket.AF_INET, "93.184.216.34"), secure=False, timeout=1)
        connection.sock = connection.transport = client
        stopped = threading.Event()

        def trickle():
            try:
                server.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                while not stopped.wait(0.02):
                    server.sendall(b"a")
            except OSError:
                pass

        worker = threading.Thread(target=trickle, daemon=True)
        worker.start()
        started = time.monotonic()
        try:
            with patch.object(p, "REQUEST_TIMEOUT", 0.1), patch.object(p, "_resolve", return_value=[(socket.AF_INET, "93.184.216.34")]), patch.object(p, "_PinnedConnection", return_value=connection):
                with self.assertRaises(p.PodcastError):
                    p._download("http://feeds.example.com/rss")
            self.assertLess(time.monotonic() - started, 1)
        finally:
            stopped.set()
            worker.join(timeout=1)
            client.close()
            server.close()


class PodcastEndpointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        with p._lock:
            p._cache.clear()
            p._cache_size = 0
            p._clients.clear()
            p._inflight.clear()
            for events in p._budgets.values():
                events.clear()

    def test_routes_are_library_only(self):
        self.assertEqual(reverse("library:podcast_search"), "/library/podcasts/search/")
        self.assertEqual(resolve("/library/podcasts/episodes/").func, p.podcast_episodes)

    def test_get_only(self):
        self.assertEqual(p.podcast_search(self.factory.post("/" )).status_code, 405)

    def test_invalid_query_and_feed_errors_are_json(self):
        for view, query in ((p.podcast_search, {}), (p.podcast_search, {"q": "x" * 121}), (p.podcast_episodes, {"feed": "http://localhost/feed"})):
            response = view(self.factory.get("/", query))
            self.assertEqual(response.status_code, 400)
            self.assertIn("error", json.loads(response.content))

    def test_search_returns_normalized_metadata_and_caches_without_database(self):
        directory = {"results": [{"collectionId": 42, "collectionName": "A Podcast", "artistName": "Host", "feedUrl": FEED_URL, "artworkUrl600": "https://media.example.com/cover.jpg"}, {"feedUrl": "http://127.0.0.1/rss"}, {"feedUrl": 12}]}
        with patch.object(p, "_download", return_value=(json.dumps(directory).encode(), "https://itunes.apple.com/search")) as download:
            first = p.podcast_search(self.factory.get("/", {"q": "Example show"}))
            second = p.podcast_search(self.factory.get("/", {"q": "example SHOW"}))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.content, second.content)
        self.assertEqual(len(json.loads(first.content)["shows"]), 1)
        self.assertEqual(download.call_count, 1)
        self.assertTrue(download.call_args.args[0].startswith("https://itunes.apple.com/search?"))

    def test_episode_endpoint_has_metadata_only_contract(self):
        with patch.object(p, "_download", return_value=(RSS, FEED_URL)):
            response = p.podcast_episodes(self.factory.get("/", {"feed": FEED_URL}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(len(json.loads(response.content)["episodes"]), 2)

    def test_upstream_and_invalid_json_errors(self):
        with patch.object(p, "_download", side_effect=p.PodcastError("Provider unavailable")):
            response = p.podcast_search(self.factory.get("/", {"q": "science"}))
        self.assertEqual(response.status_code, 502)
        with patch.object(p, "_download", return_value=(b"[]", "https://itunes.apple.com/")):
            response = p.podcast_search(self.factory.get("/", {"q": "news"}))
        self.assertEqual(response.status_code, 502)

    def test_client_limit_ignores_spoofed_forwarded_header(self):
        request = self.factory.get("/", {"q": "science"}, HTTP_X_FORWARDED_FOR="1.2.3.4")
        with patch.object(p, "_search", return_value={"shows": []}):
            for _ in range(60):
                self.assertEqual(p.podcast_search(request).status_code, 200)
            response = p.podcast_search(request)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "60")

    def test_upstream_budget_and_cache_hit_exemption(self):
        loader = MagicMock(return_value={"shows": []})
        for i in range(20):
            p._cached("search", str(i), loader)
        p._cached("search", "0", loader)
        with self.assertRaises(p.PodcastError) as caught:
            p._cached("search", "new", loader)
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(loader.call_count, 20)

    def test_cache_expiry_entry_limit_and_byte_budget(self):
        loader = MagicMock(return_value={"shows": []})
        with patch.object(p.time, "monotonic", return_value=100):
            p._cached("search", "one", loader)
        with patch.object(p.time, "monotonic", return_value=1001):
            p._cached("search", "one", loader)
        self.assertEqual(loader.call_count, 2)
        with patch.object(p, "CACHE_ENTRIES", 2):
            p._cached("feed", "two", loader)
            p._cached("feed", "three", loader)
            p._cached("feed", "four", loader)
        self.assertEqual(len(p._cache), 2)
        with patch.object(p, "CACHE_BYTES", 1):
            p._cached("feed", "oversize", loader)
        self.assertNotIn(("feed", "oversize"), p._cache)

    def test_concurrency_and_duplicate_request_limits_release_after_failure(self):
        p._inflight.add(("feed", "same"))
        with self.assertRaises(p.PodcastError) as caught:
            p._cached("feed", "same", lambda: {})
        self.assertEqual(caught.exception.status, 503)
        with patch.object(p, "_network_slots") as slots:
            slots.acquire.return_value = False
            with self.assertRaises(p.PodcastError):
                p._cached("feed", "busy", lambda: {})
            slots.acquire.return_value = True
            with self.assertRaises(p.PodcastError):
                p._cached("feed", "fail", lambda: (_ for _ in ()).throw(p.PodcastError("Failure")))
            slots.release.assert_called_once()
            self.assertNotIn(("feed", "fail"), p._inflight)
