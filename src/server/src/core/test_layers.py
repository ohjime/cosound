"""A layer's timing, from the post to the row and back to the player.

The part that must never move is the hash: a Cosound is found again by a hash
of its layers, and every mix saved before layers had timing was hashed without
any. These pin that a layer at the default timing still hashes exactly as it
always did, by re-deriving the key the way the code did before timing existed.
"""

import hashlib
import json
from decimal import ROUND_UP, Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.utils import serialize_mix
from core.layers import LayerSpec
from core.models import Cosound, Sound, SoundLayer
from library.models import SoundMix
from library.utils import parse_layers


def legacy_hashid(layers):
    """Cosound.compute_hashid as it was written before layers had timing."""
    normalized = []
    for sound_id, gain in layers:
        gain = Decimal(str(gain))
        rounded = (gain * 2).quantize(Decimal("0.1"), rounding=ROUND_UP) / 2
        normalized.append((sound_id, rounded))
    normalized.sort(key=lambda t: t[0])
    key = "".join(f"{sid}@{g}&" for sid, g in normalized).rstrip("&")
    return hashlib.sha256(key.encode()).hexdigest()


def make_sound(title):
    return Sound.objects.create(
        file=f"sounds/{title.lower()}.wav",
        title=title,
        published=True,
        embeddings=[0, 0, 0, 0, 0],
    )


class HashStabilityTests(TestCase):
    def test_a_mix_saved_before_timing_hashes_as_it_always_did(self):
        mixes = [
            [(12, 0.5), (3, 0.8)],
            [(7, 1.0), (7, 0.33), (2, 0.0)],
            [(41, 0.2749)],
        ]
        for layers in mixes:
            with self.subTest(layers=layers):
                self.assertEqual(Cosound.compute_hashid(layers), legacy_hashid(layers))

    def test_a_post_at_the_default_timing_hashes_like_one_without_any(self):
        posted = [
            {"sound_id": 12, "sound_gain": 0.5, "playback_rate": 1, "stretch": 1.75,
             "second_copy": True, "repetitions": 1, "cycle_rest": 0, "start_delay": 0,
             "phase_step": 0, "phase_hold": 4, "phase_hold_alt": 4},
            {"sound_id": 3, "sound_gain": 0.8},
        ]
        _, layers = parse_layers(json.dumps(posted))

        self.assertEqual(Cosound.compute_hashid(layers), legacy_hashid([(12, 0.5), (3, 0.8)]))

    def test_timing_makes_a_different_mix_and_the_same_timing_the_same_one(self):
        plain = LayerSpec(sound_id=5, gain=Decimal("0.5"))
        spaced = LayerSpec(sound_id=5, gain=Decimal("0.5"), stretch=Decimal("2.5"))
        also_spaced = LayerSpec(sound_id=5, gain=Decimal("0.5"), stretch=Decimal("2.50"))

        self.assertNotEqual(Cosound.compute_hashid([plain]), Cosound.compute_hashid([spaced]))
        self.assertEqual(Cosound.compute_hashid([spaced]), Cosound.compute_hashid([also_spaced]))

    def test_settings_that_change_nothing_do_not_change_the_hash(self):
        plain = LayerSpec(sound_id=5, gain=Decimal("0.5"))
        # Repeats with no rest to end a cycle play exactly as one repeat does.
        counted = LayerSpec(sound_id=5, gain=Decimal("0.5"), repetitions=6)
        # Holds with no slip to hold for, or a slip with no second copy to slip.
        held = LayerSpec(sound_id=5, gain=Decimal("0.5"), phase_hold=9)
        alone = LayerSpec(
            sound_id=5, gain=Decimal("0.5"), second_copy=False, phase_step=Decimal("0.125")
        )
        lone = LayerSpec(sound_id=5, gain=Decimal("0.5"), second_copy=False)

        hashid = Cosound.compute_hashid
        self.assertEqual(hashid([counted]), hashid([plain]))
        self.assertEqual(hashid([held]), hashid([plain]))
        self.assertEqual(hashid([alone]), hashid([lone]))

    def test_a_second_pitch_and_turns_are_keyed_only_when_they_change_something(self):
        plain = LayerSpec(sound_id=5, gain=Decimal("0.5"))
        spaced = LayerSpec(sound_id=5, gain=Decimal("0.5"), stretch=Decimal("2.5"))
        hashid = Cosound.compute_hashid

        # A key from before these existed is untouched by their defaults.
        self.assertEqual(
            spaced.normalized().timing_key(),
            "~r1.00s2.50c1n1w0.0d0.0p0.000h4k4",
        )
        # A second rate equal to the first, a gap without turns, or either
        # without a second copy plays exactly as the layer did.
        same = LayerSpec(sound_id=5, gain=Decimal("0.5"), playback_rate_b=Decimal("1.00"))
        gap_only = LayerSpec(sound_id=5, gain=Decimal("0.5"), turn_gap=Decimal("4"))
        lone = LayerSpec(sound_id=5, gain=Decimal("0.5"), second_copy=False)
        lone_turns = LayerSpec(
            sound_id=5, gain=Decimal("0.5"), second_copy=False,
            playback_rate_b=Decimal("0.5"), take_turns=True, turn_gap=Decimal("2"),
        )
        self.assertEqual(hashid([same]), hashid([plain]))
        self.assertEqual(hashid([gap_only]), hashid([plain]))
        self.assertEqual(hashid([lone_turns]), hashid([lone]))

        pitched = LayerSpec(sound_id=5, gain=Decimal("0.5"), playback_rate_b=Decimal("0.5"))
        turns = LayerSpec(sound_id=5, gain=Decimal("0.5"), take_turns=True, turn_gap=Decimal("2"))
        self.assertNotEqual(hashid([pitched]), hashid([plain]))
        self.assertNotEqual(hashid([turns]), hashid([plain]))
        self.assertNotEqual(
            hashid([turns]),
            hashid([LayerSpec(sound_id=5, gain=Decimal("0.5"), take_turns=True, turn_gap=Decimal("3"))]),
        )
        # Taking turns ignores the spacing and the slip, so they do not key.
        self.assertEqual(
            hashid([turns]),
            hashid([LayerSpec(
                sound_id=5, gain=Decimal("0.5"), take_turns=True, turn_gap=Decimal("2"),
                stretch=Decimal("3"), phase_step=Decimal("0.25"),
            )]),
        )

    def test_the_sound_set_hash_ignores_timing_and_takes_bare_ids(self):
        spaced = LayerSpec(sound_id=5, gain=Decimal("0.5"), stretch=Decimal("3"))
        self.assertEqual(Cosound.compute_hashset([spaced]), Cosound.compute_hashset([(5, 1)]))
        self.assertEqual(Cosound.compute_hashset([5]), Cosound.compute_hashset([(5, 1)]))


class ParseLayersTests(TestCase):
    def test_timing_is_clamped_snapped_and_defaulted(self):
        posted = [{
            "sound_id": "9",
            "sound_gain": 3,
            "playback_rate": 9,
            "stretch": 1.73,
            "second_copy": "false",
            "repetitions": 40,
            "cycle_rest": 12.3,
            "start_delay": -5,
            "phase_step": 0.1251,
            "phase_hold": "not a number",
        }]
        _, [layer] = parse_layers(json.dumps(posted))

        self.assertEqual(layer.sound_id, 9)
        self.assertEqual(layer.gain, Decimal("1.0"))
        self.assertEqual(layer.playback_rate, Decimal("2.00"))
        self.assertEqual(layer.stretch, Decimal("1.75"))
        self.assertIs(layer.second_copy, False)
        self.assertEqual(layer.repetitions, 16)
        self.assertEqual(layer.cycle_rest, Decimal("12.5"))
        self.assertEqual(layer.start_delay, Decimal("0.0"))
        self.assertEqual(layer.phase_step, Decimal("0.125"))
        self.assertEqual(layer.phase_hold, 4)
        self.assertEqual(layer.phase_hold_alt, 4)

    def test_the_second_pitch_and_turns_are_read_clamped_and_defaulted(self):
        posted = [
            {"sound_id": 1, "playback_rate_b": 0.12, "take_turns": "true", "turn_gap": 90},
            {"sound_id": 2, "playback_rate_b": None, "turn_gap": "nope"},
            {"sound_id": 3},
        ]
        _, [clamped, blank, missing] = parse_layers(json.dumps(posted))

        self.assertEqual(clamped.playback_rate_b, Decimal("0.25"))
        self.assertIs(clamped.take_turns, True)
        self.assertEqual(clamped.turn_gap, Decimal("60.0"))
        for layer in (blank, missing):
            self.assertIsNone(layer.playback_rate_b)
            self.assertIs(layer.take_turns, False)
            self.assertEqual(layer.turn_gap, Decimal("0.0"))

    def test_layers_without_a_sound_are_still_skipped(self):
        posted = [{"sound_id": "draft-1"}, {"sound_gain": 1}, [], {"sound_id": 4}]
        _, layers = parse_layers(json.dumps(posted))
        self.assertEqual([layer.sound_id for layer in layers], [4])

    def test_a_post_that_is_not_a_list_is_invalid(self):
        self.assertEqual(parse_layers("5"), (None, None))
        self.assertEqual(parse_layers("{nope"), (None, None))


class TimingRoundTripTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="mixer", email="mixer@example.com", password="pw"
        )
        cls.rain = make_sound("Rain")
        cls.birds = make_sound("Birds")

    def test_saved_timing_comes_back_to_the_player(self):
        timing = {
            "playback_rate": 0.75, "stretch": 1.0, "second_copy": True, "repetitions": 3,
            "cycle_rest": 30.0, "start_delay": 4.5, "phase_step": 0.125, "phase_hold": 2,
            "phase_hold_alt": 5, "playback_rate_b": 1.5, "take_turns": False, "turn_gap": 0.0,
        }
        posted = [
            {"sound_id": self.rain.pk, "sound_gain": 0.5, **timing},
            {"sound_id": self.birds.pk, "sound_gain": 1},
        ]
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("library:save_confirm"),
            {"layers": json.dumps(posted), "title": "Timed"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

        row = SoundLayer.objects.get(sound=self.rain)
        self.assertEqual(row.timing(), timing)
        mix = SoundMix.objects.get(creator=self.user)
        by_title = {layer["sound_title"]: layer for layer in mix.cosound.as_layers()}
        self.assertEqual({key: by_title["Rain"][key] for key in timing}, timing)
        self.assertEqual(by_title["Birds"]["stretch"], 1.75, "the default two drifting copies")
        saved = {layer["sound_title"]: layer for layer in serialize_mix(mix)["layers"]}
        self.assertEqual({key: saved["Rain"][key] for key in timing}, timing)

    def test_saving_the_same_mix_again_finds_the_same_cosound(self):
        posted = json.dumps([{"sound_id": self.rain.pk, "sound_gain": 0.5, "cycle_rest": 10}])
        _, layers = parse_layers(posted)
        first = Cosound.get_or_create_from_layers(layers)
        _, again = parse_layers(posted)

        self.assertEqual(Cosound.get_or_create_from_layers(again), first)
        self.assertEqual(Cosound.objects.count(), 1)
