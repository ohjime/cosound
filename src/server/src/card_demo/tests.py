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
        self.assertTrue(all(sound["gain"] == 50 for sound in response.context["sounds"]))
        self.assertNotContains(response, "Demo sound 9")

    def test_page_is_ui_only(self):
        response = self.client.get(reverse("card_demo:index"))

        self.assertContains(response, "data-card-demo")
        self.assertContains(response, "data-card-demo-tools")
        self.assertContains(response, 'data-theme="dim"')
        self.assertContains(response, 'data-light-mode="true"')
        self.assertNotContains(response, "data-card-theme-toggle")
        self.assertNotContains(response, "Activate light mode")
        self.assertNotContains(response, "toggleLightMode")
        self.assertContains(response, "data-card-hue-slider")
        self.assertContains(response, "data-ring-paper-hue-slider")
        self.assertContains(response, "Ring + paper")
        self.assertNotContains(response, "data-page-hue-slider")
        self.assertContains(response, "data-card-width-slider")
        self.assertContains(response, "data-card-height-slider")
        self.assertContains(response, "data-card-scale-slider")
        self.assertContains(response, "data-card-gap-slider")
        self.assertContains(response, "data-print-sheet")
        self.assertContains(response, "data-print-card-slot")
        self.assertContains(response, "US Letter print sheet preview")
        self.assertContains(response, "width: 8.5in")
        self.assertContains(response, "height: 11in")
        self.assertContains(response, "--effective-card-width")
        self.assertContains(response, "--effective-card-height")
        self.assertContains(response, "--page-surface: hsl(var(--ring-hue) 18% 20%)")
        self.assertNotContains(response, "--page-hue")
        self.assertContains(response, "height: 31.5rem")
        self.assertContains(response, "border-radius: 1.125rem")
        self.assertContains(response, "box-shadow: 0 0 0 8px var(--ring-surface)")
        self.assertContains(response, "ring-8")
        self.assertNotContains(response, "ring-[1.5rem]")
        self.assertContains(response, "data-card-demo-sounds")
        self.assertContains(response, "data-card-demo-indicator")
        self.assertContains(response, "data-card-demo-indicator-text")
        self.assertContains(response, "min-w-0 w-full truncate")
        self.assertContains(response, "data-flavor-text-input")
        self.assertContains(response, "data-flavor-size-slider")
        self.assertContains(response, "data-card-demo-flavor-box")
        self.assertContains(response, "h-[9.25rem] shrink-0 overflow-hidden")
        self.assertContains(response, 'class="h-full overflow-hidden px-4 py-2"')
        self.assertContains(response, 'aria-label="Flavor text area"')
        self.assertContains(response, "data-indicator-text-input")
        self.assertContains(response, "data-indicator-size-slider")
        self.assertContains(response, "data-indicator-centered-toggle")
        self.assertContains(response, "data-master-text-input")
        self.assertContains(response, "data-card-demo-master-text")
        self.assertContains(response, "bg-[#f3f4f6]")
        self.assertContains(response, 'style="color: #2d2d2d"')
        self.assertContains(response, "data-left-arrow-toggle")
        self.assertContains(response, "data-right-arrow-toggle")
        self.assertContains(response, "data-bottom-arrow-toggle")
        self.assertContains(response, "data-bottom-arrow-slider")
        self.assertContains(response, 'x-show="showLeftArrow"')
        self.assertContains(response, 'x-show="showRightArrow"')
        self.assertContains(response, 'x-show="showBottomArrow"')
        self.assertContains(response, "data-card-demo-bottom-arrow")
        self.assertContains(response, "data-artwork-upload")
        self.assertContains(response, 'accept="image/*"')
        self.assertContains(response, "data-artwork-error")
        self.assertContains(response, "data-artwork-text-toggle")
        self.assertContains(response, "data-artwork-title-input")
        self.assertContains(response, "data-artist-name-input")
        self.assertContains(response, "data-artwork-text-size-slider")
        self.assertContains(response, "data-card-demo-artwork-text")
        self.assertContains(response, 'x-show="showArtworkText"')
        self.assertContains(response, "data-like-button-toggle")
        self.assertContains(response, "data-card-demo-like")
        self.assertContains(response, 'x-show="showLikeButton"')
        self.assertContains(response, 'aria-label="Previous carousel panel"')
        self.assertContains(response, 'aria-label="Next carousel panel"')
        self.assertContains(response, 'aria-label="Current layer volume"')
        self.assertContains(response, "fill-current opacity-0", count=2)
        self.assertContains(response, "Mute this layer")
        self.assertContains(response, "Isolate this layer")
        self.assertContains(response, "data-card-demo-master")
        self.assertContains(response, "data-card-demo-master-shell")
        self.assertContains(response, "data-card-demo-artwork")
        self.assertContains(response, "overflow-hidden rounded-t-2xl")
        self.assertNotContains(response, 'x-text="index + 1"')
        self.assertNotContains(response, "currentLayer?.sound_title")
        self.assertNotContains(response, "currentLayer?.sound_artist")
        self.assertNotContains(response, "currentLayer?.tags")
        self.assertNotContains(response, "currentLayer?.flavor")
        self.assertNotContains(response, "No flavor text yet.")
        self.assertNotContains(response, "Add to favourite sounds")
        self.assertNotContains(response, "Remove from favourite sounds")
        self.assertNotContains(response, ':disabled="isFirst"')
        self.assertNotContains(response, "join-item")
        self.assertNotContains(response, 'aria-label="Lower all Sounds"')
        self.assertNotContains(response, "Pause this Cosound")
        self.assertNotContains(response, 'aria-label="Save this Cosound"')
        self.assertNotContains(response, 'aria-label="Raise all Sounds"')
        self.assertNotContains(response, 'id="card-demo-deck"')
        self.assertNotContains(response, 'id="card-demo-header"')
        self.assertNotContains(response, 'id="card-demo-figure"')
        self.assertNotContains(response, 'id="card-demo-body"')
        self.assertNotContains(response, 'id="card-demo-master"')
        self.assertNotContains(response, "<audio")
        self.assertNotContains(response, "sound_file")
        self.assertNotContains(response, "data-cosound-mixer-root")
        self.assertNotContains(response, "hx-post")
