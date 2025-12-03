"""
Check Supabase test_bt_devices table directly
"""

import requests

# Direct values from Django .env
SUPABASE_URL = "https://bjieozmcptbxgbvzpfyc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJqaWVvem1jcHRieGdidnpwZnljIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MjU1NDU3NiwiZXhwIjoyMDc4MTMwNTc2fQ.dlZvMXA82ahKBSelTeDAPwRb2k3PewEyEKIGbrvuCUg"

print("=" * 60)
print("Checking Supabase test_bt_devices table")
print("=" * 60)
print()

# Query all devices
url = f"{SUPABASE_URL}/rest/v1/test_bt_devices?select=*"
headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}'
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    devices = response.json()
    print(f"✅ Found {len(devices)} device(s) in database:")
    print()
    
    for i, device in enumerate(devices, 1):
        print(f"{i}. Device:")
        print(f"   ID: {device.get('id')}")
        print(f"   User ID: {device.get('user_id')}")
        print(f"   MAC: {device.get('device_mac')}")
        print(f"   Name: {device.get('device_name')}")
        print(f"   Status: {device.get('status')}")
        print(f"   Last Seen: {device.get('last_seen')}")
        print(f"   Created: {device.get('created_at')}")
        print()
else:
    print(f"❌ Error: {response.status_code}")
    print(f"Response: {response.text}")

print()
print("=" * 60)
print("Checking test_bt_sessions table")
print("=" * 60)
print()

# Query all sessions
url = f"{SUPABASE_URL}/rest/v1/test_bt_sessions?select=*&order=connected_at.desc&limit=10"
response = requests.get(url, headers=headers)

if response.status_code == 200:
    sessions = response.json()
    print(f"✅ Found {len(sessions)} session(s) in database:")
    print()
    
    for i, session in enumerate(sessions, 1):
        print(f"{i}. Session:")
        print(f"   ID: {session.get('id')}")
        print(f"   Device ID: {session.get('device_id')}")
        print(f"   Connected: {session.get('connected_at')}")
        print(f"   Disconnected: {session.get('disconnected_at')}")
        print(f"   Status: {session.get('status')}")
        print()
else:
    print(f"❌ Error: {response.status_code}")
    print(f"Response: {response.text}")

print("=" * 60)
