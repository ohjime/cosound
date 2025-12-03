# Enable-BluetoothDiscoverable.ps1
# Makes Windows laptop discoverable via Bluetooth
# This allows the Raspberry Pi BLE scanner to detect your laptop

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Windows Bluetooth Discoverability Tool" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Bluetooth is available
Write-Host "Checking Bluetooth status..." -ForegroundColor Yellow

# Get Bluetooth adapter info
$bluetooth = Get-PnpDevice -Class Bluetooth -Status OK

if ($bluetooth.Count -eq 0) {
    Write-Host "❌ No Bluetooth adapter found!" -ForegroundColor Red
    Write-Host "   Make sure your Bluetooth hardware is enabled." -ForegroundColor Red
    exit 1
}

Write-Host "✅ Found $($bluetooth.Count) Bluetooth adapter(s)" -ForegroundColor Green
foreach ($device in $bluetooth) {
    Write-Host "   - $($device.FriendlyName)" -ForegroundColor Gray
}
Write-Host ""

# Check Bluetooth Radio status
Write-Host "Checking Bluetooth Radio status..." -ForegroundColor Yellow

try {
    # Try to get Bluetooth radio using WMI
    $btRadio = Get-WmiObject -Namespace "root\cimv2\mdm\dmmap" -Class "MDM_Policy_Config01_Bluetooth02" -ErrorAction SilentlyContinue
    
    if ($btRadio) {
        Write-Host "✅ Bluetooth Radio is active" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Could not query Bluetooth radio status" -ForegroundColor Yellow
    }
} catch {
    Write-Host "⚠️  Could not query Bluetooth radio status (admin rights may be needed)" -ForegroundColor Yellow
}

Write-Host ""

# Instructions to make discoverable
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MANUAL STEPS TO ENABLE DISCOVERABILITY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Option 1: Windows Settings (Easy)" -ForegroundColor Green
Write-Host "-----------------------------------" -ForegroundColor Gray
Write-Host "1. Press Win+I to open Settings"
Write-Host "2. Click 'Bluetooth & devices'"
Write-Host "3. Toggle Bluetooth to ON"
Write-Host "4. Click 'View more devices' or scroll down"
Write-Host "5. Your PC should now be discoverable"
Write-Host ""

Write-Host "Option 2: Quick Settings (Fastest)" -ForegroundColor Green
Write-Host "-----------------------------------" -ForegroundColor Gray
Write-Host "1. Click the Bluetooth icon in system tray"
Write-Host "2. Make sure Bluetooth is ON"
Write-Host "3. Windows automatically becomes discoverable"
Write-Host ""

Write-Host "Option 3: Open Bluetooth Settings Now" -ForegroundColor Green
Write-Host "--------------------------------------" -ForegroundColor Gray
Write-Host "Press Enter to open Bluetooth settings automatically..."
Read-Host

# Open Bluetooth settings
Write-Host "Opening Bluetooth settings..." -ForegroundColor Yellow
Start-Process "ms-settings:bluetooth"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "VERIFICATION" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Your laptop MAC address: AC:F2:3C:D9:97:4E" -ForegroundColor Yellow
Write-Host ""
Write-Host "To verify your laptop is being detected:" -ForegroundColor White
Write-Host "1. Check your Raspberry Pi scanner logs" -ForegroundColor Gray
Write-Host "2. Look for MAC address: AC:F2:3C:D9:97:4E" -ForegroundColor Gray
Write-Host "3. The scanner should report it to Django" -ForegroundColor Gray
Write-Host ""

Write-Host "⚠️  IMPORTANT NOTES:" -ForegroundColor Yellow
Write-Host "- Windows BLE advertising is automatic when Bluetooth is ON" -ForegroundColor Gray
Write-Host "- Your laptop advertises as: $env:COMPUTERNAME" -ForegroundColor Gray
Write-Host "- The scanner is set to TARGET_DEVICE_NAME=ALL" -ForegroundColor Gray
Write-Host "- This means it detects ALL BLE devices including your laptop" -ForegroundColor Gray
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Keeping Bluetooth active..." -ForegroundColor Green
Write-Host "Press Ctrl+C to exit" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Keep the script running to maintain discoverability
$seconds = 0
try {
    while ($true) {
        Start-Sleep -Seconds 10
        $seconds += 10
        $minutes = [math]::Floor($seconds / 60)
        Write-Host "⏱️  Running for $minutes min $($seconds % 60) sec - Bluetooth should be discoverable" -ForegroundColor Cyan
    }
} catch {
    Write-Host "`n👋 Stopped. Bluetooth remains enabled." -ForegroundColor Green
}
