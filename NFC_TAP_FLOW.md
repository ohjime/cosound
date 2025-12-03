# NFC Tap Flow Implementation

## Overview
Added `tap` gating mechanism - Django only creates sessions when user explicitly taps NFC tag.

## Flow

### 1. User Taps NFC Tag
```
NFC Tag → Opens Browser → Loads Web App → Calls /api/nfc-tap
```

**Endpoint:** `POST /api/nfc-tap`
```json
{
  "user_id": "00d7e8e1-55c9-4173-b780-5b17de7d820d"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Tap registered, ready to detect device",
  "device_mac": "AC:F2:3C:D9:97:4E"
}
```

**What happens:** Sets `tap = true` in `test_bt_devices` for user's device

### 2. Raspberry Pi Detects Device
```
Scanner detects MAC → Calls /api/scanner/device-detected
```

**Django checks:**
- Is device registered? ✅
- Is `tap = true`? ✅ → Create session & set `tap = false`
- Is `tap = false`? ❌ → Ignore detection

### 3. Session Created
- New row in `test_bt_sessions` with `status = 'active'`
- Device `tap` set to `false` (consumed)
- Device `status` set to `'connected'`

### 4. Device Disconnects
- Status changes to `'disconnected'`
- Session ends with `disconnected_at` timestamp
- `tap` remains `false` until next NFC scan

## Setup Instructions

### 1. Run SQL in Supabase SQL Editor
```bash
# Copy entire file contents
setup_all_triggers.sql
```

This will:
- Add `tap BOOLEAN DEFAULT false` column to `test_bt_devices`
- Create triggers that check `tap = true` before creating sessions
- Auto-consume tap by setting `tap = false` after session creation

### 2. Update Web App
When NFC tag is scanned and browser opens, call:

```javascript
// On page load after NFC tap
fetch('http://10.29.148.151:8000/api/nfc-tap', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    user_id: '00d7e8e1-55c9-4173-b780-5b17de7d820d' // From Supabase auth
  })
})
```

### 3. Django Already Updated
- `services.py`: Only connects if `tap = true`, then sets `tap = false`
- `views.py`: New `/api/nfc-tap` endpoint
- `urls.py`: Route added

## Database Schema

### test_bt_devices
```sql
-- New column
tap BOOLEAN DEFAULT false  -- Set true on NFC tap, consumed on session creation
```

## Trigger Logic (Supabase)

```sql
CREATE OR REPLACE FUNCTION create_session_on_connect()
RETURNS TRIGGER AS $$
BEGIN
  -- Only create session if tap = true
  IF NEW.status = 'connected' AND NEW.tap = true THEN
    INSERT INTO test_bt_sessions (...) VALUES (...);
    NEW.tap := false;  -- Consume the tap
  END IF;
  RETURN NEW;
END;
$$;
```

## Testing

### Test 1: Normal Flow
```bash
# 1. Simulate NFC tap
curl -X POST http://10.29.148.151:8000/api/nfc-tap \
  -H "Content-Type: application/json" \
  -d '{"user_id": "00d7e8e1-55c9-4173-b780-5b17de7d820d"}'

# 2. Raspberry Pi detects device (happens automatically)
# Result: Session created ✅

# 3. Check status
curl "http://10.29.148.151:8000/api/my-status?user_id=00d7e8e1-55c9-4173-b780-5b17de7d820d"
# Should show: status='connected', tap=false
```

### Test 2: No Tap (Should Ignore)
```bash
# 1. Don't call /api/nfc-tap

# 2. Raspberry Pi detects device
# Result: Detection ignored, no session created ❌

# 3. Check Supabase
# device status stays 'disconnected', no new session
```

## Key Features

✅ **NFC-gated sessions** - Only creates sessions when user taps NFC tag  
✅ **Tap consumption** - Each tap consumed after use, prevents auto-reconnects  
✅ **Backward compatible** - Existing devices work, just need to call `/api/nfc-tap`  
✅ **Database triggers** - Automatic tap consumption in Supabase  
✅ **Django logic** - Service layer checks tap before connecting  

## Files Changed

1. `setup_all_triggers.sql` - Added tap column & trigger logic
2. `src/server-bt-django/bluetooth_api/services.py` - Check tap before connecting
3. `src/server-bt-django/bluetooth_api/views.py` - New `/api/nfc-tap` endpoint
4. `src/server-bt-django/bluetooth_api/urls.py` - Added route

## Next Steps

1. ✅ Run `setup_all_triggers.sql` in Supabase SQL Editor
2. Add NFC tap detection to web app (call `/api/nfc-tap` on load)
3. Test flow with Raspberry Pi scanner
4. Verify sessions only created after NFC tap
