import os
import json
import argparse
from app.player import SoundDevicePlayer
from app.client import (
    get_sound,
    get_latest_manifest,
)
from app.devices import detect_output
from app.conditioning import condition_manifest
from app.tui import CosoundPlayerApp
from app.utils import get_or_read_api_key

ROOT_DIR = os.path.join(os.path.dirname(__file__), "..")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
CONDITIONED_DIR = os.path.join(ROOT_DIR, "conditioned")
CONFIG_PATH = os.path.join(ROOT_DIR, "cosound.json")


def list_output_devices() -> None:
    devices = SoundDevicePlayer.available_output_devices()
    print("Available output devices:")
    for index, device in devices:
        max_output = int(device.get("max_output_channels", 0))
        name = device.get("name", "Unknown")
        print(f"  [{index}] {name} (max_output_channels={max_output})")


def setup(api_key: str, target_fs: int):

    # Get Latest Manifest from Server (DUMMY)
    manifest = get_latest_manifest(api_key)

    # Ensure the assets directory exists before reading from it
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # Remove downloaded sounds not in Latest Manifest to save space (skip dirs)
    for sound in os.listdir(ASSETS_DIR):
        path = os.path.join(ASSETS_DIR, sound)
        if os.path.isfile(path) and sound not in manifest.keys():
            os.remove(path)

    # Download and save all sounds in Latest Manfiest
    for sound_id, remote_path in manifest.items():
        local_path = get_sound(sound_id, remote_path)
        # Update Manifest to point to Local Path
        manifest[sound_id] = local_path

    # Offline conditioning pass: decode/resample/loudness/loop-fix/de-harsh once
    # so even lossy sources play back cleanly. Manifest now points at the cache.
    print(f"Conditioning {len(manifest)} sound(s) @ {target_fs} Hz…")
    manifest = condition_manifest(manifest, CONDITIONED_DIR, target_fs)

    config = {"API_KEY": api_key, "MANIFEST": manifest}

    # Save Config to Root Directory
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

    return manifest


def main(
    token: str | None = None,
    master_gain: float = 0.7,
    channels: int = 0,
    output_device: str | None = None,
):
    api_key = token or os.environ.get("COSOUND_API_KEY") or get_or_read_api_key()

    # Auto-detect the output so we can condition audio to its native rate.
    device = detect_output(output_device)
    print(f"Output: {device.name} — {device.channels}ch @ {device.samplerate} Hz")

    manifest = setup(api_key, device.samplerate)
    player = SoundDevicePlayer(
        channels=channels,
        master_gain=master_gain,
        device=output_device,
    )
    print(f"Speaker layout: {player.layout.describe()}")
    app = CosoundPlayerApp(api_key=api_key, manifest=manifest, player=player)
    app.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=None, help="Player API key")
    parser.add_argument(
        "--master-gain",
        type=float,
        default=float(os.environ.get("COSOUND_MASTER_GAIN", "0.7")),
        help="Master output gain, 0.0 to 1.0 (default 0.7)",
    )
    parser.add_argument(
        "--channels",
        type=int,
        default=int(os.environ.get("COSOUND_OUTPUT_CHANNELS", "0")),
        help="Output channels. 0 means use the device maximum.",
    )
    parser.add_argument(
        "--output-device",
        default=os.environ.get("COSOUND_OUTPUT_DEVICE"),
        help="Output device index or name substring. Default uses system default output.",
    )
    parser.add_argument(
        "--list-output-devices",
        action="store_true",
        help="Print output devices and exit.",
    )
    args = parser.parse_args()
    if args.list_output_devices:
        list_output_devices()
        raise SystemExit(0)
    main(
        token=args.token,
        master_gain=args.master_gain,
        channels=args.channels,
        output_device=args.output_device,
    )
