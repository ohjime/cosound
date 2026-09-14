import json

from django.test import TestCase
from django.urls import reverse

from core.models import (
    AlgorithmDecision,
    Cosound,
    Listener,
    Manager,
    PlaybackExposure,
    Player,
    Sound,
    User,
)
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


class PlayerExposureApiTests(TestCase):
    def setUp(self):
        manager_user = User.objects.create_user(
            username="api-manager",
            email="api-manager@example.com",
        )
        manager = Manager.objects.create(user=manager_user, name="Manager")
        self.player = Player.objects.create(manager=manager, name="Player")
        decision = AlgorithmDecision.objects.create(
            player=self.player,
            policy_version="test-v1",
            outcome="selected",
        )
        self.exposure = PlaybackExposure.objects.create(
            player=self.player,
            opening_decision=decision,
            mix_key="1@1.000000",
            layers=[{"sound_id": 1, "sound_gain": 1.0}],
        )
        self.player.current_exposure = self.exposure
        self.player.save(update_fields=["current_exposure"])

    @property
    def auth_headers(self):
        return {"X-API-Key": self.player.token}

    def test_player_response_adds_backward_compatible_exposure_ids(self):
        response = self.client.get("/api/player", headers=self.auth_headers)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["exposure_id"], str(self.exposure.exposure_id))
        self.assertEqual(
            payload["decision_id"],
            str(self.exposure.opening_decision_id),
        )
        self.assertIn("layers", payload)

    def test_acknowledgement_is_authenticated_and_idempotent(self):
        path = f"/api/exposures/{self.exposure.exposure_id}/ack"
        response = self.client.post(
            path,
            data=json.dumps({"transition_seconds": 10}),
            content_type="application/json",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.exposure.refresh_from_db()
        first_acknowledged_at = self.exposure.acknowledged_at
        self.assertEqual(self.exposure.status, PlaybackExposure.PLAYER_ACKNOWLEDGED)
        self.assertEqual(self.exposure.transition_seconds, 10)

        repeated = self.client.post(
            path,
            data=json.dumps({"transition_seconds": 30}),
            content_type="application/json",
            headers=self.auth_headers,
        )

        self.assertEqual(repeated.status_code, 200)
        self.exposure.refresh_from_db()
        self.assertEqual(self.exposure.acknowledged_at, first_acknowledged_at)
        self.assertEqual(self.exposure.transition_seconds, 10)

    def test_another_player_cannot_acknowledge_the_exposure(self):
        other = Player.objects.create(manager=self.player.manager, name="Other")

        response = self.client.post(
            f"/api/exposures/{self.exposure.exposure_id}/ack",
            data=json.dumps({"transition_seconds": 10}),
            content_type="application/json",
            headers={"X-API-Key": other.token},
        )

        self.assertEqual(response.status_code, 404)
        self.exposure.refresh_from_db()
        self.assertIsNone(self.exposure.acknowledged_at)

    def test_exposure_that_is_no_longer_current_cannot_be_acknowledged(self):
        self.player.current_exposure = None
        self.player.save(update_fields=["current_exposure"])

        response = self.client.post(
            f"/api/exposures/{self.exposure.exposure_id}/ack",
            data=json.dumps({"transition_seconds": 10}),
            content_type="application/json",
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, 404)
        self.exposure.refresh_from_db()
        self.assertIsNone(self.exposure.acknowledged_at)
