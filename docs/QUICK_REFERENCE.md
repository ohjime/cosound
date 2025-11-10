# 🚀 Display Name & Leaderboard - Quick Reference

## 📋 Database Migration (Run First!)

```sql
ALTER TABLE profiles ADD COLUMN display_name TEXT;
```

---

## 🔌 API Endpoints

### Set Display Name
```http
POST /api/auth/display-name
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "display_name": "MusicFan"
}
```

### Get Profile (includes display_name)
```http
GET /api/auth/profile
Authorization: Bearer <JWT>
```

### Get Leaderboard (Public - Top 10)
```http
GET /api/leaderboard
```

### Get My Stats
```http
GET /api/leaderboard/me
Authorization: Bearer <JWT>
```

---

## ⚡ Quick Test (PowerShell)

```powershell
# Set your JWT
$JWT = "your-token-here"

# Test display name
Invoke-RestMethod -Uri "http://localhost:3000/api/auth/display-name" `
  -Method POST `
  -Headers @{ "Authorization" = "Bearer $JWT"; "Content-Type" = "application/json" } `
  -Body '{"display_name":"TestUser"}'

# Get leaderboard (public)
Invoke-RestMethod -Uri "http://localhost:3000/api/leaderboard"

# Get my stats
Invoke-RestMethod -Uri "http://localhost:3000/api/leaderboard/me" `
  -Headers @{ "Authorization" = "Bearer $JWT" }
```

---

## 📁 Files Changed

✅ `src/server/middleware/auth.js` - Added display_name to user object  
✅ `src/server/routes/auth.js` - Added display-name endpoint  
✅ `src/server/routes/leaderboard.js` - **NEW** - Leaderboard endpoints  
✅ `src/server/index.js` - Registered leaderboard routes  

---

## 📚 Documentation

📖 **Full API Docs:** `docs/LEADERBOARD_API_DOCUMENTATION.md`  
🧪 **Testing Guide:** `docs/BACKEND_TESTING_GUIDE.md`  
🗄️ **Migration Guide:** `docs/migrations/001_add_display_name.md`  
📝 **Implementation Summary:** `docs/IMPLEMENTATION_SUMMARY.md`  

---

## 🎯 Key Features

✅ **Privacy First** - Real names stay private  
✅ **No Uniqueness** - Multiple users can share display names  
✅ **Smart Fallback** - display_name → first name → "Anonymous"  
✅ **Monthly Reset** - Leaderboard resets each calendar month  
✅ **Public Leaderboard** - No auth needed to view top 10  
✅ **Personal Stats** - Users can see their own stats  

---

## 🔒 Validation Rules

**Display Name:**
- ❌ Cannot be empty or whitespace
- ✅ Max 50 characters
- ✅ Trimmed automatically
- ✅ Special characters/emoji allowed
- ✅ Duplicates allowed

---

## 🚦 Response Examples

### Success (Display Name Set)
```json
{
  "success": true,
  "message": "Display name updated",
  "data": {
    "id": "uuid",
    "display_name": "TestUser"
  }
}
```

### Leaderboard
```json
{
  "success": true,
  "month": "November 2025",
  "count": 3,
  "data": [
    {
      "user_id": "uuid",
      "display_name": "TopVoter",
      "total_votes": 100,
      "positive_votes": 75,
      "negative_votes": 25
    }
  ]
}
```

### Error
```json
{
  "error": "Display name required"
}
```

---

## 🎨 Frontend Integration Snippet

```javascript
// Set display name
const setDisplayName = async (jwt, name) => {
  const res = await fetch('/api/auth/display-name', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${jwt}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ display_name: name })
  });
  return res.json();
};

// Get leaderboard
const getLeaderboard = async () => {
  const res = await fetch('/api/leaderboard');
  const { data } = await res.json();
  return data; // Array of top 10 voters
};

// Get my stats
const getMyStats = async (jwt) => {
  const res = await fetch('/api/leaderboard/me', {
    headers: { 'Authorization': `Bearer ${jwt}` }
  });
  const { data } = await res.json();
  return data; // Your stats object
};
```

---

## ✅ Deployment Checklist

- [ ] Run database migration
- [ ] Restart backend server
- [ ] Test all 4 endpoints
- [ ] Verify error responses
- [ ] Check authentication works
- [ ] Confirm public endpoints work without auth
- [ ] Review documentation
- [ ] Share API docs with frontend team

---

## 🐛 Troubleshooting

**"Route not found"** → Restart server, check index.js imports  
**"Authentication required"** → Check JWT format: `Bearer <token>`  
**Empty leaderboard** → Create some votes for current month  
**Display name not saving** → Verify migration ran successfully  

---

## 📞 Next Steps

1. ✅ Run database migration
2. ✅ Restart backend server
3. ✅ Test with provided scripts
4. 🎨 Frontend integration
5. 🚀 Deploy to production

---

**Status:** ✅ Backend Complete  
**Last Updated:** November 9, 2025
