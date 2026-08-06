import os
import json
import argparse
from app.player import SoundDevicePlayer
from app.client import (
    get_sound,
    get_latest_manifest,
)
from app.devices import detect_output, detect_input, list_input_devices
from app.automix import MicGainController
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


def list_input_devices_cli() -> None:
    devices = list_input_devices()
    print("Available input devices:")
    for index, device in devices:
        max_input = int(device.get("max_input_channels", 0))
        name = device.get("name", "Unknown")
        print(f"  [{index}] {name} (max_input_channels={max_input})")


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
    master_gain: float = 0.05,
    channels: int = 0,
    output_device: str | None = None,
    auto_gain: bool = True,
    input_device: str | None = None,
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

    # If a microphone is available, let it raise the master gain live —
    # otherwise fall back to the fixed/manual gain above. The slider still
    # sets the ceiling (max_gain); the mic scales it up toward that ceiling
    # as the room gets louder, and down toward a quiet floor as it quiets.
    mic_controller = None
    if auto_gain:
        mic = detect_input(input_device)
        if mic is not None:
            print(
                f"Microphone: {mic.name} — auto gain enabled "
                f"(ceiling {master_gain:.2f}, calibrating…)"
            )
            mic_controller = MicGainController(
                player, device=input_device, max_gain=master_gain
            )
            mic_controller.start()
        else:
            print("Microphone: none detected — auto gain disabled")

    app = CosoundPlayerApp(
        api_key=api_key, manifest=manifest, player=player, mic_controller=mic_controller
    )
    try:
        app.run()
    finally:
        if mic_controller is not None:
            mic_controller.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=None, help="Player API key")
    parser.add_argument(
        "--master-gain",
        type=float,
        default=float(os.environ.get("COSOUND_MASTER_GAIN", "0.05")),
        help="Master output gain ceiling, 0.0 to 1.0 (default 0.05). With a "
        "mic and auto gain enabled, this is the max volume; it only ever "
        "gets scaled down as the room gets louder.",
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
    parser.add_argument(
        "--input-device",
        default=os.environ.get("COSOUND_INPUT_DEVICE"),
        help="Input device (microphone) index or name substring. Default uses "
        "the system default input.",
    )
    parser.add_argument(
        "--no-auto-gain",
        dest="auto_gain",
        action="store_false",
        help="Disable microphone-driven master gain, even if a mic is present.",
    )
    parser.add_argument(
        "--list-input-devices",
        action="store_true",
        help="Print input devices and exit.",
    )
    args = parser.parse_args()
    if args.list_output_devices:
        list_output_devices()
        raise SystemExit(0)
    if args.list_input_devices:
        list_input_devices_cli()
        raise SystemExit(0)
    main(
        token=args.token,
        master_gain=args.master_gain,
        channels=args.channels,
        output_device=args.output_device,
        auto_gain=args.auto_gain,
        input_device=args.input_device,
    )
