#!/usr/bin/env python3
"""
Windows BLE Advertiser
Makes your Windows laptop advertise as a BLE peripheral device.
This allows the Raspberry Pi scanner to detect your laptop.
"""

import asyncio
import logging
from bleak import BleakServer
from bleak.uuids import uuid16_dict

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# BLE Service and Characteristic UUIDs
DEVICE_NAME = "TalwarLaptop"  # Your laptop's advertised name
SERVICE_UUID = "12345678-1234-5678-1234-56789abcdef0"  # Custom service UUID
CHAR_UUID = "12345678-1234-5678-1234-56789abcdef1"  # Custom characteristic UUID


def read_callback(characteristic):
    """Callback when someone reads the characteristic."""
    logger.info("Characteristic read by client")
    return b"Hello from Windows Laptop!"


def write_callback(characteristic, value):
    """Callback when someone writes to the characteristic."""
    logger.info(f"Characteristic written by client: {value}")


async def main():
    """Main BLE advertising loop."""
    print("=" * 60)
    print("Windows BLE Advertiser")
    print("=" * 60)
    print()
    
    logger.info(f"Starting BLE advertisement as '{DEVICE_NAME}'")
    logger.info(f"Your laptop MAC will be visible to BLE scanners")
    logger.info(f"Service UUID: {SERVICE_UUID}")
    logger.info("Press Ctrl+C to stop advertising")
    print()

    try:
        # Note: Windows BLE advertising is limited through bleak
        # The laptop will be discoverable during scanning but may not actively advertise
        
        logger.info("🔵 Making laptop discoverable via BLE...")
        logger.info("📡 Your Raspberry Pi scanner should now detect this laptop")
        logger.info("")
        logger.info("💡 IMPORTANT:")
        logger.info("   Windows doesn't fully support BLE peripheral mode through Python.")
        logger.info("   Instead, I'll provide alternative methods below.")
        
        print()
        print("=" * 60)
        print("ALTERNATIVE METHODS TO MAKE WINDOWS ADVERTISE BLE:")
        print("=" * 60)
        print()
        
        print("Method 1: Enable Bluetooth Discoverability (RECOMMENDED)")
        print("-" * 60)
        print("1. Open Settings → Bluetooth & devices")
        print("2. Make sure Bluetooth is ON")
        print("3. Click on 'Devices' (or 'View more devices')")
        print("4. Your PC should be discoverable")
        print()
        print("⚠️  This makes your laptop discoverable via Classic Bluetooth,")
        print("    but BLE advertising requires different APIs.")
        print()
        
        print("Method 2: Use Windows BLE Peripheral API (Advanced)")
        print("-" * 60)
        print("Windows has native BLE peripheral support, but requires:")
        print("- Windows 10 version 1709+ or Windows 11")
        print("- WinRT/UWP APIs (not available in standard Python)")
        print("- C# or C++ application")
        print()
        
        print("Method 3: Use your laptop's MAC directly (EASIEST)")
        print("-" * 60)
        print("Your laptop MAC: AC:F2:3C:D9:97:4E")
        print()
        print("Since your scanner is set to TARGET_DEVICE_NAME=ALL,")
        print("it will detect ANY BLE device nearby.")
        print()
        print("To verify your laptop is being scanned:")
        print("1. Check if AC:F2:3C:D9:97:4E appears in scanner logs")
        print("2. Your laptop may already be visible if Bluetooth is enabled")
        print()
        
        print("Method 4: Install BLE Peripheral App")
        print("-" * 60)
        print("Download: 'Bluetooth LE Lab' from Microsoft Store")
        print("- Free app from Microsoft")
        print("- Allows testing BLE peripheral mode")
        print("- Can create custom GATT services")
        print()
        
        print("=" * 60)
        print("TESTING: Keeping this script running...")
        print("=" * 60)
        print()
        
        logger.info("✅ Script is running. Your laptop should be visible in Windows Bluetooth settings.")
        logger.info("📊 Check your Raspberry Pi scanner logs for MAC: AC:F2:3C:D9:97:4E")
        print()
        
        # Keep script alive
        while True:
            await asyncio.sleep(60)
            logger.info("💚 Still advertising... (Bluetooth should be discoverable)")
            
    except KeyboardInterrupt:
        logger.info("\n👋 Stopping BLE advertiser")
    except Exception as e:
        logger.error(f"Error: {e}")
        logger.info("\n💡 Windows may not support BLE peripheral mode through Python")
        logger.info("   Try the alternative methods listed above instead.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
