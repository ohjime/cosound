from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from core.models import Manager, Player, Sound


ALGORITHM_FIELDS = [
    "algorithm_refresh_interval_seconds",
    "algorithm_active_listener_minutes",
    "algorithm_sleep_after_minutes",
    "algorithm_min_layers",
    "algorithm_max_layers",
    "algorithm_minimum_hold_seconds",
    "algorithm_maximum_stay_seconds",
    "algorithm_disagreement_penalty",
    "algorithm_exploration_probability",
    "algorithm_exploration_size",
    "baseline",
]


class PlayerProgramAlgorithmParameterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username="algorithm-admin",
            email="algorithm-admin@example.com",
            password="pw",
        )
        cls.manager = Manager.objects.create(
            user=cls.admin,
            name="Algorithm manager",
        )
        cls.player = Player.objects.create(
            manager=cls.manager,
            name="Algorithm player",
        )
        cls.program = cls.player.program
        cls.baseline_sound = Sound.objects.create(
            file="sounds/baseline.wav",
            title="Baseline",
            embeddings=[0] * 5,
        )
        cls.outside_sound = Sound.objects.create(
            file="sounds/outside.wav",
            title="Outside sound",
            embeddings=[0] * 5,
        )

    def make_unsaved_program(self, **overrides):
        program = type(self.program)(post=self.program.post)
        for field, value in overrides.items():
            setattr(program, field, value)
        return program

    def admin_fields(self, **overrides):
        fields = {
            "post": self.program.post_id,
            "collection": [self.baseline_sound.pk],
            "algorithm_refresh_interval_seconds": 45,
            "algorithm_active_listener_minutes": 10,
            "algorithm_sleep_after_minutes": 60,
            "algorithm_min_layers": 1,
            "algorithm_max_layers": 4,
            "algorithm_minimum_hold_seconds": 75,
            "algorithm_maximum_stay_seconds": 300,
            "algorithm_disagreement_penalty": 0.4,
            "algorithm_exploration_probability": 0.2,
            "algorithm_exploration_size": 3,
            "baseline": self.baseline_sound.pk,
        }
        fields.update(overrides)
        return fields

    def test_new_program_copies_algorithm_defaults(self):
        program = self.program

        self.assertEqual(
            program.algorithm_refresh_interval_seconds,
            settings.COSOUND_REFRESH_INTERVAL_SECONDS,
        )
        self.assertEqual(
            program.algorithm_min_layers,
            settings.COSOUND_MIN_LAYERS,
        )
        self.assertEqual(
            program.algorithm_max_layers,
            settings.COSOUND_MAX_LAYERS,
        )
        self.assertEqual(
            program.algorithm_active_listener_minutes,
            settings.COSOUND_ACTIVE_LISTENER_MINUTES,
        )
        self.assertEqual(
            program.algorithm_sleep_after_minutes,
            settings.COSOUND_SLEEP_AFTER_MINUTES,
        )
        self.assertEqual(
            program.algorithm_minimum_hold_seconds,
            settings.COSOUND_MINIMUM_HOLD_SECONDS,
        )
        self.assertEqual(
            program.algorithm_maximum_stay_seconds,
            settings.COSOUND_MAX_STAY_SECONDS,
        )
        self.assertEqual(
            program.algorithm_disagreement_penalty,
            settings.COSOUND_DISAGREEMENT_PENALTY,
        )
        self.assertEqual(
            program.algorithm_exploration_probability,
            settings.COSOUND_EXPLORATION_PROBABILITY,
        )
        self.assertEqual(
            program.algorithm_exploration_size,
            settings.COSOUND_EXPLORATION_SIZE,
        )
        self.assertIsNone(program.baseline)
        self.assertEqual(
            self.player.state_refresh_interval_seconds,
            settings.PLAYER_STATE_REFRESH_INTERVAL_SECONDS,
        )

    def test_cross_field_validation_rejects_inverted_ranges(self):
        cases = [
            (
                {
                    "algorithm_min_layers": 4,
                    "algorithm_max_layers": 3,
                },
                "algorithm_max_layers",
            ),
            (
                {
                    "algorithm_minimum_hold_seconds": 121,
                    "algorithm_maximum_stay_seconds": 120,
                },
                "algorithm_maximum_stay_seconds",
            ),
            (
                {
                    "algorithm_active_listener_minutes": 6,
                    "algorithm_sleep_after_minutes": 5,
                },
                "algorithm_sleep_after_minutes",
            ),
        ]

        for overrides, error_field in cases:
            with self.subTest(error_field=error_field):
                program = self.make_unsaved_program(**overrides)
                with self.assertRaises(ValidationError) as raised:
                    program.full_clean()
                self.assertIn(error_field, raised.exception.message_dict)

    def test_database_constraint_rejects_an_inverted_layer_range(self):
        original_max_layers = self.program.algorithm_max_layers

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                type(self.program).objects.filter(pk=self.program.pk).update(
                    algorithm_min_layers=4,
                    algorithm_max_layers=3,
                )

        self.program.refresh_from_db()
        self.assertEqual(self.program.algorithm_max_layers, original_max_layers)

    def test_float_validation_rejects_every_non_finite_value(self):
        for field in (
            "algorithm_disagreement_penalty",
            "algorithm_exploration_probability",
        ):
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, value=value):
                    program = self.make_unsaved_program(**{field: value})
                    with self.assertRaises(ValidationError) as raised:
                        program.full_clean()
                    self.assertIn(
                        "Enter a finite number.",
                        raised.exception.message_dict[field],
                    )

    def test_baseline_must_belong_to_the_program_collection(self):
        self.program.collection.add(self.baseline_sound)
        self.program.baseline = self.baseline_sound
        self.program.full_clean()
        self.program.save(update_fields=["baseline"])
        self.assertEqual(self.baseline_sound.baseline_programs.get(), self.program)

        self.program.baseline = self.outside_sound
        with self.assertRaises(ValidationError) as raised:
            self.program.full_clean()

        self.assertEqual(
            raised.exception.message_dict["baseline"],
            ["The baseline must be in this program's sound collection."],
        )

    def test_program_admin_exposes_and_persists_algorithm_parameters(self):
        self.client.force_login(self.admin)
        change_url = reverse(
            "admin:core_playerprogram_change",
            args=[self.program.pk],
        )

        response = self.client.get(change_url)
        self.assertContains(response, "Algorithm Tuning")
        self.assertContains(response, "Baseline")
        for field in ALGORITHM_FIELDS:
            with self.subTest(field=field):
                self.assertContains(response, f'id="id_{field}"')

        response = self.client.post(change_url, self.admin_fields())

        self.assertEqual(response.status_code, 302)
        self.program.refresh_from_db()
        self.assertEqual(self.program.algorithm_refresh_interval_seconds, 45)
        self.assertEqual(self.program.algorithm_active_listener_minutes, 10)
        self.assertEqual(self.program.algorithm_sleep_after_minutes, 60)
        self.assertEqual(self.program.algorithm_min_layers, 1)
        self.assertEqual(self.program.algorithm_max_layers, 4)
        self.assertEqual(self.program.algorithm_minimum_hold_seconds, 75)
        self.assertEqual(self.program.algorithm_maximum_stay_seconds, 300)
        self.assertEqual(self.program.algorithm_disagreement_penalty, 0.4)
        self.assertEqual(self.program.algorithm_exploration_probability, 0.2)
        self.assertEqual(self.program.algorithm_exploration_size, 3)
        self.assertEqual(self.program.baseline, self.baseline_sound)
        self.assertEqual(
            list(self.program.collection.all()),
            [self.baseline_sound],
        )

    def test_player_admin_only_exposes_the_device_runtime_poll(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("admin:core_player_change", args=[self.player.pk])
        )

        self.assertContains(response, "Device Runtime")
        self.assertContains(response, 'id="id_state_refresh_interval_seconds"')
        for field in ALGORITHM_FIELDS:
            with self.subTest(field=field):
                self.assertNotContains(response, f'id="id_{field}"')

    def test_program_admin_rejects_an_invalid_parameter_combination(self):
        self.client.force_login(self.admin)
        original_max_layers = self.program.algorithm_max_layers

        response = self.client.post(
            reverse("admin:core_playerprogram_change", args=[self.program.pk]),
            self.admin_fields(
                algorithm_min_layers=4,
                algorithm_max_layers=3,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Maximum layers cannot be lower than minimum layers.",
        )
        self.program.refresh_from_db()
        self.assertEqual(self.program.algorithm_max_layers, original_max_layers)
