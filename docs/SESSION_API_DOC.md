# Session System Quick Reference

## 🎯 How It Works

**User opens app** → Auto check-in (1-hour session created)  
**Model queries** → Only gets users with unexpired sessions  
**After 1 hour** → User automatically excluded (no manual action needed)

---

## 🗄️ Database Setup (Run First!)

```sql
CREATE TABLE sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  checked_in_at TIMESTAMPTZ DEFAULT NOW(),
  expires_at TIMESTAMPTZ NOT NULL,
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_active ON sessions(status, expires_at);
```

---

## 🔌 API Endpoints

### 1. Check-in (Auto on page load)
```http
POST /api/checkin
Authorization: Bearer <JWT>
```

**Response:**
```json
{
  "success": true,
  "message": "1-hour vibe pass activated",
  "data": {
    "session_id": "uuid",
    "expires_at": "2025-11-09T15:00:00Z",
    "expires_in_minutes": 60
  }
}
```

---

### 2. Get Session Status
```http
GET /api/session
Authorization: Bearer <JWT>
```

**Response (Active):**
```json
{
  "success": true,
  "active": true,
  "data": {
    "session_id": "uuid",
    "checked_in_at": "2025-11-09T14:00:00Z",
    "expires_at": "2025-11-09T15:00:00Z",
    "minutes_remaining": 42
  }
}
```

**Response (Inactive):**
```json
{
  "success": true,
  "active": false,
  "message": "No active session"
}
```

---

### 3. Manual Checkout (Optional)
```http
POST /api/checkout
Authorization: Bearer <JWT>
```

**Response:**
```json
{
  "success": true,
  "message": "Checked out successfully"
}
```

---

### 4. Get Active Users (For ML Model)
```http
GET /api/model/active-users
X-API-Key: <MODEL_API_KEY>
```

**Response:**
```json
{
  "success": true,
  "count": 3,
  "timestamp": "2025-11-09T14:30:00Z",
  "data": [
    {
      "user_id": "uuid-1",
      "display_name": "MusicFan",
      "checked_in_at": "2025-11-09T14:00:00Z",
      "expires_at": "2025-11-09T15:00:00Z",
      "preferences": [0.5, 0.8, 0.2, 1.0, 0.0]
    },
    {
      "user_id": "uuid-2",
      "display_name": "BeatLover",
      "checked_in_at": "2025-11-09T14:15:00Z",
      "expires_at": "2025-11-09T15:15:00Z",
      "preferences": [0.3, 0.6, 0.9, 0.1, 0.7]
    }
  ]
}
```

---

## 🎨 Frontend Integration

### Auto Check-in on Page Load

```javascript
// In your main App component or page load
useEffect(() => {
  const autoCheckin = async () => {
    const { data: { session } } = await supabase.auth.getSession();
    
    if (!session?.access_token) return;
    
    try {
      const response = await fetch('/api/checkin', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json'
        }
      });
      
      const result = await response.json();
      
      if (result.success) {
        console.log('✅ Checked in - expires at:', result.data.expires_at);
      }
    } catch (err) {
      console.error('Check-in failed:', err);
    }
  };
  
  autoCheckin();
}, []);
```

---

### Display Session Timer (Optional)

```javascript
function SessionTimer() {
  const [minutesLeft, setMinutesLeft] = useState(null);
  
  useEffect(() => {
    const checkSession = async () => {
      const response = await fetch('/api/session', {
        headers: {
          'Authorization': `Bearer ${jwt}`
        }
      });
      
      const result = await response.json();
      
      if (result.active) {
        setMinutesLeft(result.data.minutes_remaining);
      }
    };
    
    checkSession();
    
    // Update every minute
    const interval = setInterval(checkSession, 60000);
    
    return () => clearInterval(interval);
  }, []);
  
  if (!minutesLeft) return null;
  
  return (
    <div className="session-timer">
      🎫 Vibe Pass: {minutesLeft} min remaining
    </div>
  );
}
```

---

## 🤖 Model Integration (Python Example)

```python
import requests
import os

def get_active_users():
    """Get all currently active users for music selection"""
    response = requests.get(
        'http://localhost:3000/api/model/active-users',
        headers={'X-API-Key': os.getenv('ML_API_KEY')}
    )
    
    data = response.json()
    
    if not data['success']:
        print(f"Error: {data.get('error')}")
        return []
    
    print(f"Active users: {data['count']}")
    return data['data']

# Use in your algorithm
active_users = get_active_users()

# Each user has:
# - user_id: str
# - display_name: str
# - preferences: list of 5 floats [0-1]
# - checked_in_at: ISO timestamp
# - expires_at: ISO timestamp

# Example: Get average preferences
if active_users:
    avg_prefs = [
        sum(user['preferences'][i] for user in active_users) / len(active_users)
        for i in range(5)
    ]
    print(f"Average preferences: {avg_prefs}")
```

---

## 🧪 Testing with Postman

### Test Check-in
```
POST http://localhost:3000/api/checkin
Headers:
  Authorization: Bearer YOUR_JWT_HERE
```

### Test Get Session Status
```
GET http://localhost:3000/api/session
Headers:
  Authorization: Bearer YOUR_JWT_HERE
```

### Test Active Users (Model API)
```
GET http://localhost:3000/api/model/active-users
Headers:
  X-API-Key: YOUR_MODEL_API_KEY_HERE
```

---

## 📊 Monitoring Queries

### See currently active users
```sql
SELECT 
  p.name,
  p.display_name,
  s.checked_in_at,
  s.expires_at,
  ROUND(EXTRACT(EPOCH FROM (s.expires_at - NOW())) / 60) as mins_left
FROM sessions s
JOIN profiles p ON p.id = s.user_id
WHERE s.status = 'active'
  AND s.expires_at > NOW()
ORDER BY s.checked_in_at DESC;
```

### Count active sessions
```sql
SELECT 
  COUNT(*) FILTER (WHERE expires_at > NOW()) as active,
  COUNT(*) FILTER (WHERE expires_at <= NOW()) as expired,
  COUNT(*) as total
FROM sessions
WHERE status = 'active';
```

---

## ✅ Deployment Checklist

- [ ] Run database migration (create sessions table)
- [ ] Restart backend server
- [ ] Test POST /api/checkin
- [ ] Test GET /api/session
- [ ] Test GET /api/model/active-users
- [ ] Verify RLS policies work
- [ ] Add auto check-in to frontend
- [ ] Update ML model to use new endpoint

---

## 🎯 Key Points

✅ **No cron jobs needed** - Expiration handled by timestamp comparison  
✅ **No manual cleanup required** - Old sessions can stay in DB  
✅ **Automatic expiration** - After 1 hour, users excluded from queries  
✅ **Simple integration** - Just call /api/checkin on page load  
✅ **Privacy-preserving** - Only active users' preferences shared with model

---

**Status:** ✅ Ready to deploy  
**Next Step:** Run database migration → Test endpoints
