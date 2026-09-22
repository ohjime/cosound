from django.test import TestCase
from django.urls import reverse

from core.models import Cosound, Listener, Sound, User
from library.models import SoundMix


class AppNavigationTabsTests(TestCase):
    def test_home_page_renders_explore_center_and_library_right(self):
        response = self.client.get(reverse("app:home_initial"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="EXPLORE"')
        self.assertContains(response, reverse("explore:index"))
        self.assertContains(response, 'aria-label="LIBRARY"')
        self.assertContains(response, reverse("app:home_tab_library"))
        content = response.content.decode()
        self.assertLess(
            content.index('aria-label="EXPLORE"'),
            content.index('aria-label="LIBRARY"'),
        )

    def test_navigation_replaces_tab_content_without_a_tab_transition(self):
        response = self.client.get(reverse("app:home_initial"), HTTP_HX_REQUEST="true")

        self.assertNotContains(response, "data-swap-height")
        self.assertContains(response, 'hx-swap="innerHTML"', count=3)
        self.assertContains(response, 'hx-target="#tab_content"', count=3)
        self.assertContains(response, 'hx-sync="#tab_content:replace"', count=3)
        self.assertContains(response, 'aria-controls="tab_content"', count=3)
        self.assertNotContains(response, "htmx-swapping")


class AppTabBodyTests(TestCase):
    def test_library_stats_use_the_listener_and_saved_mix_counts(self):
        user = User.objects.create_user(
            username="stats-listener",
            email="stats-listener@example.com",
            password="password",
        )
        sounds = [
            Sound.objects.create(
                file=f"sounds/stats-{index}.wav",
                title=f"Stats sound {index}",
                embeddings=[0, 0, 0, 0, 0],
            )
            for index in range(2)
        ]
        listener = Listener.objects.create(user=user)
        listener.collection.add(*sounds)
        self.client.force_login(user)

        for index in range(3):
            cosound = Cosound.objects.create(
                hashset=f"stats-hashset-{index}",
                hashid=f"stats-hashid-{index}",
            )
            SoundMix.objects.create(creator=user, cosound=cosound)

        response = self.client.get(
            reverse("app:home_tab_library"), HTTP_HX_REQUEST="true"
        )

        self.assertContains(response, ">2</div>")
        self.assertContains(response, ">3</div>")
        self.assertContains(
            response, f'hx-get="{reverse("library:liked_list")}"'
        )
        self.assertContains(
            response, f'hx-get="{reverse("library:saved_list")}"'
        )

    def test_library_tab_renders_one_content_region(self):
        response = self.client.get(
            reverse("app:home_tab_library"), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-core-tab-body")
        self.assertNotContains(response, "data-tab-primary")
        self.assertNotContains(response, "data-tab-secondary")
        self.assertContains(response, "data-cosound-mixer-root")
        self.assertContains(response, "data-library-artwork-placeholder")
        self.assertContains(response, '"is_draft": true')
        self.assertNotContains(response, "Click anywhere to start")
        self.assertNotContains(response, "Your Mixes")

    def test_about_tab_renders_one_continuous_article(self):
        response = self.client.get(
            reverse("app:home_tab_about"), HTTP_HX_REQUEST="true"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-core-tab-body")
        self.assertNotContains(response, "data-tab-primary")
        self.assertNotContains(response, "data-tab-secondary")
        self.assertContains(response, "Sound, chosen by the room")
        self.assertContains(response, "Two sensors, two different signals")
        self.assertNotContains(response, "Read In-Depth Technical Details ↓")
        content = response.content.decode()
        self.assertLess(
            content.index("Sound, chosen by the room"),
            content.index("Two sensors, two different signals"),
        )


class AppStudioTabTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from core.models import Artist

        cls.artist_user = User.objects.create_user(
            username="tab-artist", email="tab-artist@example.com", password="pw"
        )
        Artist.objects.create(user=cls.artist_user, name="Tab Artist")
        cls.listener_user = User.objects.create_user(
            username="tab-listener", email="tab-listener@example.com", password="pw"
        )

    def home(self):
        return self.client.get(reverse("app:home_initial"), HTTP_HX_REQUEST="true")

    def test_studio_tab_is_hidden_when_signed_out(self):
        response = self.home()
        self.assertNotContains(response, 'aria-label="STUDIO"')
        self.assertNotContains(response, reverse("app:home_tab_studio"))
        # The placeholder login swaps the real tab over.
        self.assertContains(response, 'id="home-tab-studio"')

    def test_studio_tab_is_hidden_from_a_listener_without_an_artist(self):
        self.client.force_login(self.listener_user)
        self.assertNotContains(self.home(), 'aria-label="STUDIO"')

    def test_studio_tab_is_the_fourth_tab_for_an_artist(self):
        self.client.force_login(self.artist_user)
        content = self.home().content.decode()
        self.assertIn(reverse("app:home_tab_studio"), content)
        self.assertLess(
            content.index('aria-label="LIBRARY"'), content.index('aria-label="STUDIO"')
        )

    def test_studio_tab_body_refuses_non_artists(self):
        url = reverse("app:home_tab_studio")
        self.assertEqual(self.client.get(url, HTTP_HX_REQUEST="true").status_code, 403)
        self.client.force_login(self.listener_user)
        self.assertEqual(self.client.get(url, HTTP_HX_REQUEST="true").status_code, 403)

    def test_studio_tab_body_mounts_the_library_card_with_create(self):
        self.client.force_login(self.artist_user)
        response = self.client.get(
            reverse("app:home_tab_studio"), HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-cosound-mixer-root")
        self.assertContains(response, "allowCreate: true")
        self.assertContains(response, "artistName: 'Tab Artist'")
        self.assertContains(response, '"is_draft": true')
        self.assertContains(response, "Create a new sound")
        self.assertContains(response, "Use a sound from your library")
        self.assertContains(response, "Type a story for this sound")

    def test_library_tab_does_not_allow_create(self):
        response = self.client.get(
            reverse("app:home_tab_library"), HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, "allowCreate: false")
