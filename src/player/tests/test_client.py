import json
import unittest
from unittest.mock import MagicMock, patch

from app.client import acknowledge_exposure


class ExposureAcknowledgementClientTests(unittest.TestCase):
    @patch("app.client.urllib.request.urlopen")
    def test_posts_authenticated_transition_metadata(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {"status": "player_acknowledged"}
        ).encode("utf-8")
        urlopen.return_value = response

        result = acknowledge_exposure(
            "player-key",
            "exposure-id",
            transition_seconds=10,
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertTrue(request.full_url.endswith("/exposures/exposure-id/ack"))
        self.assertEqual(request.headers["X-api-key"], "player-key")
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {"transition_seconds": 10},
        )
        self.assertEqual(result["status"], "player_acknowledged")


if __name__ == "__main__":
    unittest.main()
