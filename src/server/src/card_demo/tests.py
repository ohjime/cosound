from django.test import TestCase
from django.urls import reverse

from core.models import Sound


class CardDemoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for index in range(1, 10):
            Sound.objects.create(
                published=True,
                title=f"Demo sound {index}",
                artist_legacy=f"Artist {index}",
                file=f"sounds/demo-{index}.wav",
                art=f"sound_arts/demo-{index}.jpg",
                flavor=f"Description {index}",
                embeddings=[0.0] * 5,
            )

    def test_page_uses_the_first_eight_sounds(self):
        response = self.client.get(reverse("card_demo:index"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "card_demo/index.html")
        self.assertEqual(
            [sound["sound_title"] for sound in response.context["sounds"]],
            [f"Demo sound {index}" for index in range(1, 9)],
        )
        self.assertNotContains(response, "Demo sound 9")

    def test_page_is_ui_only(self):
        response = self.client.get(reverse("card_demo:index"))

        self.assertContains(response, "data-card-demo")
        self.assertContains(response, "--card-width:")
        self.assertContains(response, "--card-height:")
        self.assertContains(response, "height: var(--card-height)")
        self.assertContains(response, "border-radius: 1.125rem")
        self.assertContains(response, "data-card-demo-sounds")
        self.assertContains(response, 'aria-label="Previous carousel panel"')
        self.assertContains(response, 'aria-label="Next carousel panel"')
        self.assertContains(response, 'aria-label="Current layer volume"')
        self.assertContains(response, "Mute this layer")
        self.assertContains(response, "Isolate this layer")
        self.assertContains(response, 'aria-label="Lower all Sounds"')
        self.assertContains(response, "Pause this Cosound")
        self.assertContains(response, 'aria-label="Save this Cosound"')
        self.assertContains(response, 'aria-label="Raise all Sounds"')
        self.assertNotContains(response, "<audio")
        self.assertNotContains(response, "sound_file")
        self.assertNotContains(response, "data-cosound-mixer-root")
        self.assertNotContains(response, "hx-post")
