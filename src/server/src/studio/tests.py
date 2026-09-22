"""Render smoke tests for the studio.

The builder is composed almost entirely of the shared soundscape card
(`c-core-sound-*`, see core/templates/cotton/core_sound_player.html), which the
library and explore posts render too. A component renamed or moved out from
under it fails silently in a template until a page is actually rendered, and
these are the pages that would notice last — so this asks each of them for real
bytes and looks for the parts of the card that must be in them.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import Artist, Sound


class StudioRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="studio-artist", email="studio-artist@example.com", password="pw"
        )
        cls.artist = Artist.objects.create(user=cls.user, name="Studio Artist")

    def setUp(self):
        self.client.force_login(self.user)

    def test_builder_fragment_renders_the_shared_card(self):
        response = self.client.get(reverse("studio:initial"), HTTP_HX_REQUEST="true")

        self.assertEqual(response.status_code, 200)
        # The store handoff and the card's own slots. The transport is not
        # checked here: the studio drives playback from c-studio-master above
        # the deck rather than from the shared one under the card.
        self.assertContains(response, 'id="soundLayers"')
        self.assertContains(response, 'id="card-header"')
        self.assertContains(response, 'id="card-figure"')
        self.assertContains(response, 'id="card-body"')

    def test_page_and_htmx_fragments_render(self):
        for name in ["studio:index", "studio:carousel", "studio:library"]:
            with self.subTest(url=name):
                response = self.client.get(
                    reverse(name), HTTP_HX_REQUEST="true"
                )
                self.assertEqual(response.status_code, 200)


class StudioTagSearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="tag-artist", email="tag-artist@example.com", password="pw"
        )
        Artist.objects.create(user=cls.user, name="Tag Artist")
        sound = Sound.objects.create(
            file="sounds/tagged.wav", title="Tagged", embeddings=[0, 0, 0, 0, 0]
        )
        sound.tags.add("Rain", "Rainforest", "Night")

    def search(self, **params):
        return self.client.get(
            reverse("studio:tag_search"), params, HTTP_HX_REQUEST="true"
        )

    def test_only_artists_may_search(self):
        self.assertEqual(self.search(q="rain").status_code, 403)

    def test_offers_existing_tags_and_no_request_link_on_an_exact_match(self):
        self.client.force_login(self.user)
        response = self.search(q="rain")
        self.assertContains(response, 'data-tag="Rain"')
        self.assertContains(response, 'data-tag="Rainforest"')
        self.assertNotContains(response, 'data-tag="Night"')
        self.assertNotContains(response, "Ask cosound to add")

    def test_leaves_out_tags_the_layer_already_has(self):
        self.client.force_login(self.user)
        response = self.search(q="rain", chosen="Rain")
        self.assertNotContains(response, 'data-tag="Rain"')
        self.assertContains(response, 'data-tag="Rainforest"')

    def test_an_unknown_tag_offers_to_ask_cosound(self):
        self.client.force_login(self.user)
        response = self.search(q="thunder")
        self.assertNotContains(response, "data-tag=")
        self.assertContains(response, "No tag matches “thunder”")
        self.assertContains(response, "Ask cosound to add it")

    def test_a_half_typed_tag_does_not_offer_the_request_link(self):
        self.client.force_login(self.user)
        response = self.search(q="nig")
        self.assertContains(response, 'data-tag="Night"')
        self.assertNotContains(response, "Ask cosound to add")

    def test_an_empty_query_answers_nothing(self):
        self.client.force_login(self.user)
        response = self.search(q="  ")
        self.assertEqual(response.content, b"")
