# Raspberry Pi 3 BLE Scanner Setup Guide

## Overview

Setup guide for configuring Raspberry Pi 3 as a BLE scanner for the CoSounds presence detection system.

**Role:** The Pi continuously scans for Bluetooth devices and reports them to the Django backend.

---

## Quick Start

### 1. Copy Scanner Script to Pi

Transfer `raspberry-pi-scanner.py` to your Raspberry Pi 3:

```bash
# From your laptop (where the file is)
scp raspberry-pi-scanner.py pi@raspberrypi.local:~/
scp .env.pi.example pi@raspberrypi.local:~/.env

# Or use a USB drive, or clone this repo on the Pi
```

### 2. Install Dependencies on Raspberry Pi

```bash
# SSH into Pi
ssh pi@raspberrypi.local

# Update system
sudo apt-get update
sudo apt-get upgrade

# Install Bluetooth tools and Python packages
sudo apt-get install bluetooth bluez python3 python3-pip

# Install Python dependencies
pip3 install bleak requests python-dotenv

# Enable Bluetooth service
sudo systemctl enable bluetooth
sudo systemctl start bluetooth
```

### 3. Configure Scanner

Edit the `.env` file on the Pi:

```bash
nano ~/.env
```

**Required values:**
```env
# Your laptop's IP address (Django backend)
DJANGO_API_URL=http://192.168.1.XXX:8000/api

# Scanner API key (must match Django .env)
SCANNER_API_KEY=your-scanner-api-key-here

# Scan interval (seconds)
SCAN_INTERVAL=10

# Scan timeout (seconds per scan)
SCAN_TIMEOUT=5.0
```

**How to find your laptop's IP:**
- Windows: `ipconfig | findstr IPv4`
- Mac: `ifconfig | grep "inet "`
- Linux: `hostname -I`

### 4. Test Scanner

```bash
# Run scanner
python3 raspberry-pi-scanner.py
```

**Expected output:**
```
============================================================
🎵 CoSounds BLE Scanner Starting...
============================================================
✅ Configuration loaded:
   Django API: http://192.168.1.XXX:8000/api
   Scan Interval: 10 seconds
   Scan Timeout: 5.0 seconds

Testing connection to Django backend...
✅ Django backend is reachable

🚀 Starting scanner loop (press Ctrl+C to stop)
============================================================

--- Scan #1 at 14:30:00 ---
🔍 Starting BLE scan...
📡 Scan complete: 3 devices found
✅ AA:BB:CC:DD:EE:FF: Reconnected
📤 Reported 1/3 devices to Django
⏳ Waiting 10s until next scan...
```

**Press Ctrl+C to stop the scanner.**

---

## Running Scanner Automatically

### Option A: Run in Background with nohup

```bash
sudo nohup python3 raspberry-pi-scanner.py > scanner.log 2>&1 &

# View logs
tail -f scanner.log
```

### Option B: Use screen (Recommended for Testing)

```bash
# Install screen
sudo apt-get install screen

# Start scanner in screen session
screen -S scanner
python3 raspberry-pi-scanner.py

# Detach: Press Ctrl+A then D
# Reattach later: screen -r scanner
```

### Option C: Create systemd Service (Recommended for Production)

Create service file:

```bash
sudo nano /etc/systemd/system/cosounds-scanner.service
```

**Paste this content:**
```ini
[Unit]
Description=CoSounds BLE Scanner
After=bluetooth.service network.target
Wants=bluetooth.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi
ExecStart=/usr/bin/python3 /home/pi/raspberry-pi-scanner.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start service:**
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable cosounds-scanner

# Start service now
sudo systemctl start cosounds-scanner

# Check status
sudo systemctl status cosounds-scanner

# View logs
sudo journalctl -u cosounds-scanner -f
```

**Manage service:**
```bash
# Stop scanner
sudo systemctl stop cosounds-scanner

# Restart scanner
sudo systemctl restart cosounds-scanner

# Disable auto-start on boot
sudo systemctl disable cosounds-scanner
```

---

## Troubleshooting

### "hciconfig not found"

```bash
sudo apt-get install bluetooth bluez
```

### "No Bluetooth adapter found"

```bash
# Check if Bluetooth is enabled
sudo systemctl status bluetooth

# Check adapter exists
hciconfig

# Should show "hci0" with "UP RUNNING"
# Restart Bluetooth if needed
sudo systemctl restart bluetooth
```

### "Permission denied"

Always run scanner with sudo or as root:
```bash
sudo python3 raspberry-pi-scanner.py
```

### "Cannot reach Django backend"

**Fix:**
- ✅ Verify Django is running on laptop: `curl http://LAPTOP_IP:8000/api/health`
- ✅ Check laptop firewall allows port 8000
- ✅ Ping laptop from Pi: `ping LAPTOP_IP`
- ✅ Verify `DJANGO_API_URL` in Pi `.env` has correct IP

### Scanner not detecting laptop

**Fix:**
- ✅ Make sure laptop Bluetooth is ON and discoverable
- ✅ Move Pi closer to laptop (BLE range ~10 meters)
- ✅ Test manual scan: `sudo hcitool lescan`
- ✅ Check Bluetooth status: `sudo hciconfig hci0`

### "Invalid API key" errors

**Fix:**
- ✅ Make sure `SCANNER_API_KEY` is **identical** in:
  - Django `.env` file on laptop
  - Pi `.env` file
- ✅ No extra spaces or quotes

---

## Testing

### 1. Check if Bluetooth is working

```bash
# Check Bluetooth adapter
sudo hciconfig hci0

# Should show:
# hci0:   Type: Primary  Bus: UART
#         BD Address: XX:XX:XX:XX:XX:XX  ACL MTU: 1021:8  SCO MTU: 64:1
#         UP RUNNING
```

### 2. Test manual BLE scan

```bash
sudo hcitool lescan

# You should see a list of nearby Bluetooth devices
# Press Ctrl+C to stop
```

### 3. Test Django connection

```bash
# Test health endpoint
curl http://YOUR_LAPTOP_IP:8000/api/health

# Should return:
# {"status":"ok","service":"bluetooth-presence-django","version":"1.0.0"}
```

### 4. Test scanner script

```bash
python3 raspberry-pi-scanner.py

# Watch for:
# - "Django backend is reachable" ✅
# - Devices found and reported
# - No connection errors
```

---

## Performance & Power

### Scan Interval Optimization

**Current settings:**
- Scan interval: 10 seconds
- Scan timeout: 5 seconds

**Power vs Responsiveness:**
- **Lower interval (5s):** More responsive, higher power usage
- **Higher interval (30s):** Lower power, slower detection

**Recommended:**
- Demo: 10 seconds
- Production: 15-20 seconds

### Power Consumption

- **Idle (scanning):** ~150mA (Pi 3 + BLE)
- **With WiFi:** ~200-250mA
- **Estimated runtime (2000mAh battery):** ~8-10 hours
- **For 24/7 operation:** Use wall adapter (5V 2.5A recommended)

---

## Network Configuration

### Static IP (Optional but Recommended)

Set static IP on Pi for reliable connection:

```bash
sudo nano /etc/dhcpcd.conf
```

**Add at the end:**
```
interface wlan0
static ip_address=192.168.1.100/24
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 8.8.8.8
```

**Restart networking:**
```bash
sudo systemctl restart dhcpcd
```

### WiFi Configuration

If not already connected:

```bash
sudo raspi-config
# Select: Network Options → Wi-Fi
# Enter SSID and password
```

---

## Monitoring & Debugging

### Check scanner logs (systemd)

```bash
# View recent logs
sudo journalctl -u cosounds-scanner -n 100

# Follow logs in real-time
sudo journalctl -u cosounds-scanner -f

# View logs with timestamps
sudo journalctl -u cosounds-scanner -f --output=short-iso
```

### Check Bluetooth status

```bash
# Check if Bluetooth is active
systemctl status bluetooth

# Check adapter info
hciconfig hci0

# Scan for devices
sudo hcitool lescan
```

### Monitor network connectivity

```bash
# Ping laptop
ping YOUR_LAPTOP_IP

# Test Django health
curl http://YOUR_LAPTOP_IP:8000/api/health

# Check WiFi connection
iwconfig wlan0
```

---

## Security Notes

**Scanner API Key:**
- The scanner authenticates with Django using `SCANNER_API_KEY`
- Keep this key secret (don't commit to Git)
- Change it in production

**Network Security:**
- Scanner connects to Django over HTTP (not HTTPS)
- For production, use HTTPS with proper SSL certificates
- Consider VPN or firewall rules to restrict access

---

## Updating Scanner Script

**To update scanner code:**

```bash
# Copy new version from laptop
scp raspberry-pi-scanner.py pi@raspberrypi.local:~/

# Restart scanner
sudo systemctl restart cosounds-scanner

# Check if running
sudo systemctl status cosounds-scanner
```

---

## Useful Commands

### Scanner Management

```bash
# Start scanner manually
python3 raspberry-pi-scanner.py

# Start as systemd service
sudo systemctl start cosounds-scanner

# Stop scanner
sudo systemctl stop cosounds-scanner

# Restart scanner
sudo systemctl restart cosounds-scanner

# Check scanner status
sudo systemctl status cosounds-scanner

# View scanner logs
sudo journalctl -u cosounds-scanner -f
```

### Bluetooth Commands

```bash
# Check Bluetooth adapter
sudo hciconfig hci0

# Scan for devices
sudo hcitool lescan

# Restart Bluetooth
sudo systemctl restart bluetooth

# Check Bluetooth status
systemctl status bluetooth
```

### System Commands

```bash
# Check WiFi connection
iwconfig wlan0

# Check IP address
hostname -I

# Reboot Pi
sudo reboot

# Shutdown Pi
sudo shutdown -h now
```

---

## Files on Raspberry Pi

**Location:** `/home/pi/`

- `raspberry-pi-scanner.py` - Scanner script
- `.env` - Configuration (not committed to Git)
- `scanner.log` - Log file (if using nohup)

---

## Notes

- **Raspberry Pi 3** has built-in Bluetooth (no dongle needed)
- **Scanner uses bleak library** for cross-platform BLE support
- **Reports ALL detected devices** to Django (Django filters for registered devices)
- **Continuous scanning** every 10 seconds
- **HTTP POST requests** to Django backend
- **Retry logic** for network failures

---

## Next Steps

After scanner is working:
- 🎯 Test with multiple devices
- 🎯 Optimize scan interval for battery life
- 🎯 Set up systemd service for auto-start
- 🎯 Monitor logs for debugging
- 🎯 Consider static IP for reliable connection

---

For complete setup instructions, see [DEMO_SETUP.md](DEMO_SETUP.md).

**Last Updated:** 2025-12-02
**Status:** Scanner-Based Implementation
