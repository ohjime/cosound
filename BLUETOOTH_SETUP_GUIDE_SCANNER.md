# Bluetooth Presence Detection - Scanner-Based Setup Guide

Complete guide for the **scanner-based** Bluetooth presence detection system.

## Overview

This system uses:
- **Raspberry Pi 3** as a BLE scanner (detects your laptop)
- **Django backend** on your laptop (manages presence logic)
- **React frontend** with device registration on NFC tap

For quick setup, see [DEMO_SETUP.md](DEMO_SETUP.md).

---

## Architecture

```
Laptop (Device) → BLE → Pi Scanner → HTTP → Django → Supabase
                                              ↑
                                         Frontend (NFC tap)
```

**Key differences from beacon approach:**
- ✅ Pi scans for devices (not advertises)
- ✅ Laptop just has Bluetooth ON (passive)
- ✅ No Web Bluetooth API needed in browser
- ✅ More reliable, backend-driven

---

## Complete Setup Instructions

See [DEMO_SETUP.md](DEMO_SETUP.md) for step-by-step instructions.

**Summary:**
1. Run database migration in Supabase
2. Setup Django backend (port 8000)
3. Setup React frontend with MAC address
4. Setup Pi scanner
5. Test end-to-end flow

---

## For detailed documentation, see:
- [DEMO_SETUP.md](DEMO_SETUP.md) - Quick setup guide
- [RASPBERRY_PI_SETUP.md](RASPBERRY_PI_SETUP.md) - Pi scanner setup
- [src/server-bt-django/README.md](src/server-bt-django/README.md) - Django backend docs
