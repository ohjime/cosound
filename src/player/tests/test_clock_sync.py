import unittest
from unittest.mock import patch

from app.sync import ServerClock


class ServerClockTests(unittest.TestCase):
    OFFSET = 1_750_000_000.0

    def observe(self, clock, sent, *, up=0.004, down=0.004, processing=0.0, offset=None):
        offset = self.OFFSET if offset is None else offset
        return clock.observe(
            sent, sent + up + offset, sent + up + processing + offset,
            sent + up + processing + down,
        )

    def test_bootstrap_excludes_server_work_and_uses_minimum_round_trip(self):
        clock = ServerClock()
        self.assertFalse(clock.ready)
        self.assertIsNone(clock.server_time(100))
        self.assertTrue(self.observe(clock, 100, up=0.030, down=0.005))
        self.assertTrue(self.observe(clock, 101, processing=0.2))
        self.assertFalse(clock.ready)
        self.assertTrue(self.observe(clock, 102, up=0.020, down=0.005))
        self.assertTrue(clock.ready)
        self.assertAlmostEqual(clock.server_time(110), self.OFFSET + 110, places=6)

    def test_different_monotonic_origins_map_to_the_same_server_deadline(self):
        first, second = ServerClock(), ServerClock()
        for index in range(3):
            self.observe(first, 100 + index)
            self.observe(second, 100_000 + index, offset=self.OFFSET - 99_900)
        self.assertAlmostEqual(first.server_time(105), second.server_time(100_005), places=6)

    def test_client_wall_clock_jump_does_not_change_mapping_or_holdover(self):
        clock = ServerClock()
        for index in range(3):
            self.observe(clock, 100 + index)
        with patch("time.time", return_value=-999_999), patch("app.sync.monotonic", return_value=150):
            self.assertAlmostEqual(clock.server_time(), self.OFFSET + 150, places=6)

    def test_old_low_delay_samples_expire_so_clock_tracks_drift(self):
        clock = ServerClock()
        for index in range(3):
            self.observe(clock, 100 + index, up=0.001, down=0.001)
        for index in range(3):
            self.observe(clock, 140 + index, offset=self.OFFSET + 0.002)
        self.assertAlmostEqual(clock.server_time(145), self.OFFSET + 145.002, places=6)

    def test_one_hour_with_100ppm_oscillator_drift_and_network_jitter(self):
        # Model true server seconds independently of a fast/slow monotonic
        # oscillator, symmetric LAN jitter, and occasional one-way queuing.
        # This is a deterministic clock simulation, not a speaker measurement.
        for ppm in (-100, 100):
            clock = ServerClock()
            rate = 1 + ppm / 1_000_000
            worst_error = 0.0
            for index in range(1801):
                true_send = index * 2.0
                jitter = (index % 7) * 0.00025
                outbound = 0.002 + jitter + (0.012 if index % 11 == 0 else 0)
                inbound = 0.002 + jitter + (0.0001 if index % 3 == 0 else 0)
                work = 0.0005
                accepted = clock.observe(
                    10_000 + true_send * rate,
                    self.OFFSET + true_send + outbound,
                    self.OFFSET + true_send + outbound + work,
                    10_000 + (true_send + outbound + work + inbound) * rate,
                )
                self.assertTrue(accepted)
                if clock.ready:
                    # Check just before the next probe, when the selected
                    # sample is oldest and oscillator bias is largest.
                    true_now = true_send + 1.999
                    estimate = clock.server_time(10_000 + true_now * rate)
                    worst_error = max(worst_error, abs(estimate - (self.OFFSET + true_now)))
            with self.subTest(ppm=ppm):
                self.assertLess(worst_error, 0.001, f"Maximum clock error: {worst_error * 1000:.3f} ms")

    def test_fresh_sample_updates_established_clock_after_a_long_gap(self):
        clock = ServerClock()
        for index in range(3):
            self.observe(clock, 100 + 2 * index)
        self.observe(clock, 120, offset=self.OFFSET + 0.002)
        self.assertAlmostEqual(clock.server_time(121), self.OFFSET + 121.002, places=6)

    def test_reset_relearns_server_step_without_interrupting_holdover(self):
        clock = ServerClock()
        for index in range(3):
            self.observe(clock, 100 + index, up=0.001, down=0.001)
        clock.reset()
        self.assertTrue(clock.ready)
        self.assertAlmostEqual(clock.server_time(105), self.OFFSET + 105, places=6)
        for index in range(3):
            self.observe(clock, 110 + index, offset=self.OFFSET + 7)
        self.assertAlmostEqual(clock.server_time(115), self.OFFSET + 122, places=6)
        clock.reset(keep_estimate=False)
        self.assertFalse(clock.ready)
        self.assertIsNone(clock.server_time())

    def test_malformed_stale_and_impossible_exchanges_do_not_poison_clock(self):
        clock = ServerClock()
        valid = (100.0, self.OFFSET + 100.004, self.OFFSET + 100.004, 100.008)
        for bad in (None, "100", True, float("nan"), float("inf"), 10 ** 400):
            for index in range(4):
                sample = list(valid)
                sample[index] = bad
                with self.subTest(bad=repr(bad), position=index):
                    self.assertFalse(clock.observe(*sample))
        for sample in (
            (-1, self.OFFSET, self.OFFSET, 0),
            (100, 0, 0, 100.008),
            (100, self.OFFSET, self.OFFSET - 1, 100.008),
            (100, self.OFFSET, self.OFFSET + 1, 100.008),
            (100, self.OFFSET, self.OFFSET, 99),
            (100, self.OFFSET, self.OFFSET, 106),
            (100, self.OFFSET, self.OFFSET, 101.1),
        ):
            self.assertFalse(clock.observe(*sample))
        self.assertFalse(clock.ready)
        self.assertTrue(clock.observe(*valid))
        self.assertFalse(clock.observe(*valid))
        self.assertFalse(self.observe(clock, 99))
        self.assertFalse(clock.ready)


if __name__ == "__main__":
    unittest.main()
