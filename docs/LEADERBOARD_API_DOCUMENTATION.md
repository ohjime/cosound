# Display Name & Leaderboard API Documentation

## Overview
This document covers the display name and leaderboard features that allow users to set a public-facing name for privacy and compete on a monthly voting leaderboard.

---

## Display Name Feature

### Why Display Names?
- **Privacy**: Users' real Google names stay private
- **Fun**: Users can choose creative nicknames
- **Simple**: No uniqueness constraint - multiple users can share names
- **Optional**: Falls back to first name from Google if not set

---

## Authentication Endpoints

### Set Display Name
Set or update the user's public display name shown on the leaderboard.

**Endpoint:** `POST /api/auth/display-name`  
**Authentication:** Required (JWT Bearer token)

#### Request Body
```json
{
  "display_name": "MusicFan"
}
```

#### Validation Rules
- **Required**: Cannot be empty or whitespace only
- **Max Length**: 50 characters
- **Uniqueness**: NOT required - duplicates allowed

#### Success Response (200 OK)
```json
{
  "success": true,
  "message": "Display name updated",
  "data": {
    "id": "user-uuid",
    "email": "user@example.com",
    "name": "John Smith",
    "display_name": "MusicFan"
  }
}
```

#### Error Responses

**400 Bad Request** - Missing display name
```json
{
  "error": "Display name required"
}
```

**400 Bad Request** - Too long
```json
{
  "error": "Display name too long (max 50 characters)"
}
```

**401 Unauthorized** - No/invalid JWT
```json
{
  "error": "Authentication required"
}
```

---

### Get Profile (Updated)
Retrieve user's profile including display name.

**Endpoint:** `GET /api/auth/profile`  
**Authentication:** Required (JWT Bearer token)

#### Success Response (200 OK)
```json
{
  "id": "user-uuid",
  "email": "user@example.com",
  "name": "John Smith",
  "display_name": "MusicFan"
}
```

**Note:** `display_name` will be `null` if not yet set.

---

## Leaderboard Endpoints

### Get Monthly Leaderboard
Get top 10 voters for the current month (public endpoint).

**Endpoint:** `GET /api/leaderboard`  
**Authentication:** Not required (public)

#### Success Response (200 OK)
```json
{
  "success": true,
  "month": "November 2025",
  "count": 10,
  "data": [
    {
      "user_id": "user-uuid-1",
      "display_name": "MusicFan",
      "total_votes": 245,
      "positive_votes": 180,
      "negative_votes": 65
    },
    {
      "user_id": "user-uuid-2",
      "display_name": "BeatLover",
      "total_votes": 198,
      "positive_votes": 150,
      "negative_votes": 48
    },
    {
      "user_id": "user-uuid-3",
      "display_name": "John",
      "total_votes": 156,
      "positive_votes": 120,
      "negative_votes": 36
    }
  ]
}
```

#### Response Fields
- **user_id**: User's unique identifier
- **display_name**: Public name (display_name if set, otherwise first name from Google, fallback to "Anonymous")
- **total_votes**: Total number of votes this month
- **positive_votes**: Count of positive votes (vote_value > 0)
- **negative_votes**: Count of negative votes (vote_value < 0)

#### Notes
- Leaderboard resets monthly (based on calendar month)
- Only shows top 10 voters
- Sorted by total_votes (descending)
- Public endpoint - no authentication needed

---

### Get My Stats
Get the authenticated user's voting statistics for the current month.

**Endpoint:** `GET /api/leaderboard/me`  
**Authentication:** Required (JWT Bearer token)

#### Success Response (200 OK)
```json
{
  "success": true,
  "month": "November 2025",
  "data": {
    "user_id": "user-uuid",
    "display_name": "MusicFan",
    "total_votes": 42,
    "positive_votes": 30,
    "negative_votes": 12
  }
}
```

#### Use Cases
- Show user their own stats even if not in top 10
- Display personal progress
- Highlight user's row in leaderboard UI

---

## Updated Authentication Middleware

The authentication middleware now includes `display_name` in the user object:

```javascript
req.user = {
  id: "user-uuid",
  email: "user@example.com",
  name: "John Smith",           // From Google OAuth
  display_name: "MusicFan"       // User's chosen display name (or null)
}
```

---

## Database Schema Requirements

### Profiles Table
Add the following column to support display names:

```sql
ALTER TABLE profiles 
ADD COLUMN display_name TEXT;
```

**No constraints needed:**
- ❌ No UNIQUE constraint (duplicates allowed)
- ❌ No NOT NULL (optional field)
- ❌ No index needed (not searching by it)

---

## Frontend Integration Examples

### 1. Check if Display Name Exists (First Login)

```javascript
async function checkDisplayName(jwt) {
  const response = await fetch('/api/auth/profile', {
    headers: { 
      'Authorization': `Bearer ${jwt}` 
    }
  });
  
  const profile = await response.json();
  
  if (!profile.display_name) {
    // Show display name setup UI
    showDisplayNamePrompt(profile.name);
  }
}
```

### 2. Set Display Name

```javascript
async function setDisplayName(jwt, displayName) {
  const response = await fetch('/api/auth/display-name', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${jwt}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ display_name: displayName })
  });
  
  const result = await response.json();
  
  if (result.success) {
    console.log('Display name set:', result.data.display_name);
  } else {
    console.error('Error:', result.error);
  }
}
```

### 3. Fetch Leaderboard (Public)

```javascript
async function getLeaderboard() {
  const response = await fetch('/api/leaderboard');
  const data = await response.json();
  
  console.log(`${data.month} Leaderboard:`);
  data.data.forEach((user, index) => {
    console.log(`${index + 1}. ${user.display_name} - ${user.total_votes} votes`);
  });
}
```

### 4. Fetch My Stats (Authenticated)

```javascript
async function getMyStats(jwt) {
  const response = await fetch('/api/leaderboard/me', {
    headers: { 
      'Authorization': `Bearer ${jwt}` 
    }
  });
  
  const result = await response.json();
  
  console.log('Your stats:', result.data);
  // { display_name: "MusicFan", total_votes: 42, ... }
}
```

---

## Privacy & Security Considerations

### Privacy Benefits
✅ **Real names protected**: Google names not shown publicly  
✅ **User control**: Users choose their public identity  
✅ **Campus-friendly**: Students can vote without exposing identity

### No Security Concerns
✅ **No uniqueness**: Eliminates username squatting  
✅ **Simple validation**: Just length check  
✅ **RLS protection**: Users can only update their own display_name

### Display Name Fallback Logic
```
1. If display_name is set → Use display_name
2. Else if Google name exists → Use first name (split on space)
3. Else → Use "Anonymous"
```

---

## Testing Checklist

### Display Name Endpoints
- [ ] Set display name successfully
- [ ] Reject empty display name
- [ ] Reject display name > 50 characters
- [ ] Require authentication
- [ ] Update existing display name
- [ ] Include display_name in profile GET

### Leaderboard Endpoints
- [ ] Public leaderboard accessible without auth
- [ ] Returns top 10 voters only
- [ ] Sorts by total_votes descending
- [ ] Correctly counts positive/negative votes
- [ ] Resets monthly (test with different months)
- [ ] Uses display_name when set
- [ ] Falls back to first name when not set
- [ ] My stats requires authentication
- [ ] My stats returns correct counts

---

## Error Handling

All endpoints follow consistent error format:

```json
{
  "error": "Human-readable error message"
}
```

Common HTTP status codes:
- **200 OK**: Success
- **201 Created**: Resource created
- **400 Bad Request**: Validation error or bad input
- **401 Unauthorized**: Missing or invalid JWT
- **500 Internal Server Error**: Server-side error

---

## Implementation Notes

### Vote Counting Logic
Votes are counted from the `vote` table:
- `vote_time >= start_of_month` filters current month
- Aggregation groups by `user_id`
- `vote_value > 0` = positive vote
- `vote_value < 0` = negative vote

### Performance Considerations
- Leaderboard query scans all votes for current month
- For large datasets, consider:
  - Caching leaderboard for 5-10 minutes
  - Adding index on `vote_time` column
  - Pre-aggregating vote counts (materialized view)

### Future Enhancements
- [ ] Historical leaderboards (previous months)
- [ ] All-time leaderboard
- [ ] Display name change history/rate limiting
- [ ] Profanity filter for display names
- [ ] Display name suggestions

---

## Quick Reference

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/api/auth/display-name` | POST | ✅ | Set display name |
| `/api/auth/profile` | GET | ✅ | Get profile (includes display_name) |
| `/api/leaderboard` | GET | ❌ | Get top 10 voters this month |
| `/api/leaderboard/me` | GET | ✅ | Get my stats this month |

---

**Last Updated:** November 9, 2025
