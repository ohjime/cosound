#!/usr/bin/env python3
"""
Raspberry Pi 3 BLE Scanner for CoSounds Presence Detection
Detects specific Bluetooth device and reports to Django backend.
"""

import asyncio
import os
import logging
import requests
from datetime import datetime, timezone
from bleak import BleakScanner
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
DJANGO_API_URL = os.getenv('DJANGO_API_URL', 'http://10.29.148.151:8000/api').rstrip('/')
DEVICE_ENDPOINT = f"{DJANGO_API_URL}/scanner/device-detected"
TARGET_DEVICE_NAME = (os.getenv('TARGET_DEVICE_NAME', '') or '').strip()
SCAN_INTERVAL = int(os.getenv('SCAN_INTERVAL', 10))
SCAN_TIMEOUT = float(os.getenv('SCAN_TIMEOUT', 5.0))

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def scan_for_devices():
    """Scan for nearby Bluetooth devices."""
    try:
        logger.debug("Starting BLE scan...")
        devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT, return_adv=True)

        detected = []
        for device, adv_data in devices.values():
            if device.address:
                detected.append({
                    'device_mac': device.address,
                    'device_name': device.name or 'Unknown Device',
                    'rssi': adv_data.rssi  # Use AdvertisementData.rssi instead of deprecated BLEDevice.rssi
                })

        return detected
    except Exception as e:
        logger.error(f"Scan error: {e}")
        return []


def report_to_django(device):
    """Report device detection to Django."""
    try:
        payload = {
            'device_mac': device['device_mac'],
            'device_name': device['device_name'],
            'rssi': device['rssi'],
            'seen_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        }

        response = requests.post(
            DEVICE_ENDPOINT,
            json=payload,
            headers={'Content-Type': 'application/json', 'User-Agent': 'cosounds-pi-scanner/1.0'},
            timeout=5,
        )

        if response.status_code == 200:
            result = response.json()
            action = result.get('action', 'unknown')

            if action == 'restored':
                logger.info("Device restored from grace period")
            elif action == 'connected':
                logger.info("Device reconnected")
            elif action == 'updated':
                logger.info("Device last_seen updated")
            else:
                logger.debug(f"Action: {action}")

            return True
        else:
            logger.error(f"HTTP {response.status_code}: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        logger.error(f"Cannot reach Django at {DJANGO_API_URL}")
        return False
    except Exception as e:
        logger.error(f"Error reporting to Django: {e}")
        return False


async def scan_loop():
    """Main scanning loop."""
    scan_count = 0

    while True:
        try:
            scan_count += 1
            logger.info(f"--- Scan #{scan_count} at {datetime.now().strftime('%H:%M:%S')} ---")

            # Scan for devices
            devices = await scan_for_devices()

            if not devices:
                logger.warning(f"No devices found. Target '{TARGET_DEVICE_NAME or 'ANY'}' not detected.")
            else:
                logger.info(f"Found {len(devices)} devices")

                # Look for target device by name OR report all if target name is empty
                target_found = False
                
                # If TARGET_DEVICE_NAME is empty or "ALL", report all devices
                if not TARGET_DEVICE_NAME or TARGET_DEVICE_NAME.upper() == "ALL":
                    logger.info(f"📡 Reporting ALL {len(devices)} detected devices")
                    for device in devices:
                        # Highlight PRANAV laptop and phone
                        mac = device['device_mac'].upper()
                        name = device['device_name']
                        if mac == 'AC:F2:3C:D9:97:4E' or 'PRANAV' in name.upper():
                            logger.info(f"   🎯 LAPTOP: {mac} ({name}) RSSI: {device['rssi']}")
                        elif mac == '50:E7:B7:36:79:A4':
                            logger.info(f"   📱 PHONE: {mac} ({name}) RSSI: {device['rssi']}")
                        else:
                            logger.info(f"   → {mac} ({name}) RSSI: {device['rssi']}")
                        report_to_django(device)
                    target_found = True
                else:
                    # Match by target device name
                    for device in devices:
                        device_name = device['device_name'] or ''
                        if TARGET_DEVICE_NAME.upper() in device_name.upper():
                            target_found = True
                            logger.info(f"🎯 TARGET FOUND: {device_name}")
                            logger.info(f"   MAC: {device['device_mac']}")
                            logger.info(f"   RSSI: {device['rssi']}")

                            if report_to_django(device):
                                logger.info(f"✅ Reported to Django successfully")
                            else:
                                logger.error(f"❌ Failed to report to Django")
                            break

                if not target_found:
                    logger.warning(f"❌ Target '{TARGET_DEVICE_NAME}' not in scan results")
                    logger.info(f"💡 Tip: Set TARGET_DEVICE_NAME=ALL to report all devices")
                    logger.info(f"   Looking for your devices:")
                    logger.info(f"      - Phone: 50:E7:B7:36:79:A4")
                    logger.info(f"      - Laptop: AC:F2:3C:D9:97:4E")
                    logger.info(f"   All detected MACs:")
                    for device in devices:
                        mac = device['device_mac'].upper()
                        if mac in ['50:E7:B7:36:79:A4', 'AC:F2:3C:D9:97:4E']:
                            logger.info(f"      ✅ FOUND: {mac} - {device['device_name']}")
                        else:
                            logger.debug(f"      - {mac}: {device['device_name']}")

            # Wait before next scan
            await asyncio.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            logger.info("\nScanner stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            await asyncio.sleep(SCAN_INTERVAL)


async def main():
    """Main entry point."""
    print("=" * 60)
    print("CoSounds BLE Scanner")
    print("=" * 60)
    print()

    # Show configuration
    logger.info("Configuration:")
    logger.info(f"   Django API: {DJANGO_API_URL}")
    logger.info(f"   Target Device: {TARGET_DEVICE_NAME or 'ANY'}")
    logger.info(f"   Scan Interval: {SCAN_INTERVAL}s")
    logger.info(f"   Scan Timeout: {SCAN_TIMEOUT}s")
    print()

    # Test Django connection
    logger.info("Testing Django connection...")
    try:
        response = requests.get(f"{DJANGO_API_URL}/health", timeout=5)
        if response.status_code == 200:
            logger.info("Django backend is reachable")
        else:
            logger.warning(f"Django returned status {response.status_code}")
    except Exception as e:
        logger.error(f"Cannot reach Django: {e}")
        logger.error("Make sure Django is running!")
        return

    print()
    logger.info("Starting scanner (press Ctrl+C to stop)")
    logger.info("=" * 60)
    print()

    # Start scanning
    await scan_loop()

    print()
    logger.info("=" * 60)
    logger.info("Scanner stopped")
    logger.info("=" * 60)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit(1)
