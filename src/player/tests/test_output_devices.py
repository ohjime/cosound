import unittest
from unittest.mock import patch

from app import devices


def fake_device(channels, name="Device", samplerate=44100.0, index=1):
    return {
        "name": name,
        "index": index,
        "hostapi": 0,
        "max_input_channels": 0,
        "max_output_channels": channels,
        "default_samplerate": samplerate,
    }


class SentinelHostApiTests(unittest.TestCase):
    """The routing-max cap belongs to ALSA/OSS, not to every host API."""

    def test_alsa_plugin_count_falls_back_to_stereo(self):
        self.assertEqual(devices._plausible_channels(128, "ALSA"), (2, True))
        self.assertEqual(devices._plausible_channels(32, "ALSA"), (2, True))

    def test_alsa_hardware_count_passes_through(self):
        self.assertEqual(devices._plausible_channels(8, "ALSA"), (8, False))

    def test_core_audio_count_is_taken_as_given(self):
        # A 22-output MOTU interface has 22 outputs; capping it here was what
        # rendered an 8.1 rig as assumed stereo.
        self.assertEqual(devices._plausible_channels(22, "Core Audio"), (22, False))
        self.assertEqual(devices._plausible_channels(9, "Core Audio"), (9, False))

    def test_jack_reports_its_ports_honestly(self):
        api = "JACK Audio Connection Kit"
        self.assertFalse(devices._uses_sentinel_counts(api))
        self.assertEqual(devices._plausible_channels(64, api), (64, False))


class DetectOutputTests(unittest.TestCase):
    def _detect(self, info, hostapi):
        with (
            patch.object(devices.sd, "query_devices", return_value=info),
            patch.object(devices.sd, "query_hostapis", return_value=[{"name": hostapi}]),
        ):
            return devices.detect_output()

    def test_multichannel_core_audio_interface_keeps_its_channels(self):
        device = self._detect(fake_device(22, name="UltraLite-mk5"), "Core Audio")
        self.assertEqual(device.channels, 22)
        self.assertFalse(device.channels_assumed)
        self.assertEqual(device.hostapi, "Core Audio")

    def test_alsa_plugin_device_is_still_assumed_stereo(self):
        device = self._detect(fake_device(128, name="default"), "ALSA")
        self.assertEqual(device.channels, 2)
        self.assertTrue(device.channels_assumed)


if __name__ == "__main__":
    unittest.main()
