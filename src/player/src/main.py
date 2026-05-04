import os
import json
import time
import argparse
from app.player import SoundDevicePlayer
from app.client import (
    get_sound,
    get_latest_cosound,
    get_latest_manifest,
)
from app.utils import (
    get_or_read_api_key,
    print_ascii_banner,
    print_cosound_state,
    print_header,
)

ROOT_DIR = os.path.join(os.path.dirname(__file__), "..")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
CONFIG_PATH = os.path.join(ROOT_DIR, "cosound.json")
REFRESH_INTERVAL = 30  # In Seconds

# Global state to share the latest cosound data across threads
global_cosound = {}


def setup(api_key: str):

    # Get Latest Manifest from Server (DUMMY)
    manifest = get_latest_manifest(api_key)

    # Remove sounds not in Latest Manifest to save space
    sounds = os.listdir(ASSETS_DIR)
    for sound in sounds:
        if sound not in manifest.keys():
            os.remove(os.path.join(ASSETS_DIR, sound))

    # Download and save all sounds in Latest Manfiest
    for sound_id, remote_path in manifest.items():
        local_path = get_sound(sound_id, remote_path)
        # Update Manifest to point to Local Path
        manifest[sound_id] = local_path

    config = {"API_KEY": api_key, "MANIFEST": manifest}

    # Save Config to Root Directory
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

    return manifest


def main(token: str | None = None):
    print_ascii_banner()
    print_header()
    api_key = token or os.environ.get("COSOUND_API_KEY") or get_or_read_api_key()
    manifest = setup(api_key)
    player = SoundDevicePlayer(channels=8)
    while True:
        cosound = get_latest_cosound(api_key)
        print_cosound_state(cosound)
        for sound_id, gain in cosound.items():
            local_path = manifest.get(str(sound_id))
            if not local_path:
                continue
            player.queue_sound(local_path, gain)
        player.dequeue_cosound()
        time.sleep(REFRESH_INTERVAL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=None, help="Player API key")
    args = parser.parse_args()
    main(token=args.token)
