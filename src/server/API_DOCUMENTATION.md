# Soundscape API Documentation

Base URL: `http://localhost:3000`

All endpoints except health check require authentication via JWT token.

---

## 🔓 Public Endpoints

### Health Check

Check if the API server is running.

**Endpoint:** `GET /health`

**Headers:** None required

**Response:**

```json
{
  "status": "ok",
  "timestamp": "2025-11-08T12:34:56.789Z"
}
```

---

## 📋 Preference Endpoints

All preference endpoints require authentication and are prefixed with `/api`

### Get User Preferences

Retrieve the current user's soundscape preferences.

**Endpoint:** `GET /api/preferences`

**Headers:**

```
Authorization: Bearer <access_token>
```

**Success Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "uuid",
    "user_id": "uuid",
    "preference": {
      "soundType": "nature",
      "volume": 0.75,
      "mood": "calm",
      "tempo": "slow",
      "instruments": ["piano", "ambient"]
    },
    "created_at": "2025-11-08T10:00:00.000Z",
    "updated_at": "2025-11-08T12:00:00.000Z"
  }
}
```

**If no preferences exist:**

```json
{
  "success": true,
  "data": null
}
```

**Error Response (401):**

```json
{
  "error": "Invalid or expired token"
}
```

---

### Save/Update User Preferences

Create new preferences or update existing ones. This endpoint automatically handles both cases.

**Endpoint:** `POST /api/preferences`

**Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body:**
Send any JSON object with your preference data. The entire object will be stored.

```json
{
  "soundType": "nature",
  "volume": 0.75,
  "mood": "calm",
  "tempo": "slow",
  "instruments": ["piano", "ambient"],
  "environmentalSounds": ["rain", "ocean"],
  "customSettings": {
    "rainIntensity": 0.6,
    "birdSounds": true
  }
}
```

**Note:** You can structure the preference object however you want. All fields are flexible.

**Success Response (200):**

```json
{
  "success": true,
  "message": "Preferences saved successfully",
  "data": {
    "id": "uuid",
    "user_id": "uuid",
    "preference": {
      "soundType": "nature",
      "volume": 0.75,
      ...
    },
    "created_at": "2025-11-08T10:00:00.000Z",
    "updated_at": "2025-11-08T12:30:00.000Z"
  }
}
```

**Error Response (401):**

```json
{
  "error": "Invalid or expired token"
}
```

**How it works:**

- **First time:** Creates a new preference record
- **Subsequent calls:** Updates the existing preference record
- The `preference` field stores your entire JSON object as text

---

## 🗳️ Vote Endpoints

All vote endpoints require authentication and are prefixed with `/api`

### Get User Votes

Retrieve all votes submitted by the current user.

**Endpoint:** `GET /api/votes`

**Headers:**

```
Authorization: Bearer <access_token>
```

**Optional Query Parameters:**

- `song` - Filter votes by song name

**Examples:**

```
GET /api/votes
GET /api/votes?song=Moonlight%20Sonata
```

**Success Response (200):**

```json
{
  "success": true,
  "data": [
    {
      "id": "uuid",
      "user_id": "uuid",
      "song": "Moonlight Sonata",
      "vote_value": 5,
      "vote_time": "2025-11-08T12:00:00.000Z"
    },
    {
      "id": "uuid",
      "user_id": "uuid",
      "song": "River Flows",
      "vote_value": 4,
      "vote_time": "2025-11-08T11:30:00.000Z"
    }
  ]
}
```

**Error Response (401):**

```json
{
  "error": "Invalid or expired token"
}
```

---

### Submit a Vote

Submit a new vote for a song.

**Endpoint:** `POST /api/votes`

**Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body:**

```json
{
  "song": "Moonlight Sonata",
  "vote_value": 5
}
```

**Required Fields:**

- `song` (string) - Name or identifier of the song
- `vote_value` (number/string) - Vote value (will be converted to integer)

**Success Response (201):**

```json
{
  "success": true,
  "message": "Vote recorded successfully",
  "data": {
    "id": "uuid",
    "user_id": "uuid",
    "song": "Moonlight Sonata",
    "vote_value": 5,
    "vote_time": "2025-11-08T12:00:00.000Z"
  }
}
```

**Error Response (400):**

```json
{
  "error": "Song and vote_value are required"
}
```

**Note:** The `vote_value` is automatically converted to an integer, so you can send `"5"` or `5`.

---

### Update a Vote

Update an existing vote.

**Endpoint:** `PUT /api/votes/:id`

**URL Parameters:**

- `id` - UUID of the vote to update

**Headers:**

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

**Request Body:**
You can update either field or both:

```json
{
  "song": "New Song Name",
  "vote_value": 3
}
```

**Example:**

```
PUT /api/votes/123e4567-e89b-12d3-a456-426614174000
```

**Success Response (200):**

```json
{
  "success": true,
  "message": "Vote updated successfully",
  "data": {
    "id": "uuid",
    "user_id": "uuid",
    "song": "New Song Name",
    "vote_value": 3,
    "vote_time": "2025-11-08T12:30:00.000Z"
  }
}
```

**Error Response (400):**

```json
{
  "error": "Vote not found or you don't have permission to update it"
}
```

**Security:** Users can only update their own votes.

---

### Delete a Vote

Delete an existing vote.

**Endpoint:** `DELETE /api/votes/:id`

**URL Parameters:**

- `id` - UUID of the vote to delete

**Headers:**

```
Authorization: Bearer <access_token>
```

**Example:**

```
DELETE /api/votes/123e4567-e89b-12d3-a456-426614174000
```

**Success Response (200):**

```json
{
  "success": true,
  "message": "Vote deleted successfully"
}
```

**Error Response (400):**

```json
{
  "error": "Vote not found or you don't have permission to delete it"
}
```

**Security:** Users can only delete their own votes.

---

## 🔧 Common Workflow Examples

### 1. User Registration & Login Flow

```javascript
// 1. Sign up
const signupResponse = await fetch("http://localhost:3000/api/auth/signup", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    email: "user@example.com",
    password: "securePassword123",
  }),
});
const { session } = await signupResponse.json();
const accessToken = session.access_token;

// 2. Save token for future requests
localStorage.setItem("access_token", accessToken);
```

### 2. Setting User Preferences

```javascript
// Get saved token
const token = localStorage.getItem("access_token");

// Save preferences
await fetch("http://localhost:3000/api/preferences", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    soundType: "nature",
    volume: 0.75,
    mood: "calm",
    instruments: ["piano", "ambient"],
  }),
});
```

### 3. Submitting a Vote

```javascript
// Get saved token
const token = localStorage.getItem("access_token");

// Submit vote
await fetch("http://localhost:3000/api/votes", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    song: "Moonlight Sonata",
    vote_value: 5,
  }),
});
```

### 4. Getting User Data

```javascript
// Get saved token
const token = localStorage.getItem("access_token");

// Get preferences
const prefResponse = await fetch("http://localhost:3000/api/preferences", {
  headers: { Authorization: `Bearer ${token}` },
});
const { data: preferences } = await prefResponse.json();

// Get votes
const votesResponse = await fetch("http://localhost:3000/api/votes", {
  headers: { Authorization: `Bearer ${token}` },
});
const { data: votes } = await votesResponse.json();
```

---

## 🚨 Error Handling

All endpoints return errors in a consistent format:

```json
{
  "error": "Error message description"
}
```

### Common HTTP Status Codes:

- `200` - Success (GET, PUT, DELETE)
- `201` - Created (POST)
- `400` - Bad Request (missing/invalid data)
- `401` - Unauthorized (missing/invalid token)
- `500` - Internal Server Error

### Example Error Handling:

```javascript
try {
  const response = await fetch("http://localhost:3000/api/preferences", {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    const error = await response.json();
    console.error("API Error:", error.error);

    if (response.status === 401) {
      // Token expired or invalid - redirect to login
      window.location.href = "/login";
    }
  }

  const data = await response.json();
  // Use data...
} catch (err) {
  console.error("Network error:", err);
}
```

---

## 🔐 Authentication Notes

1. **Token Storage:** Store the `access_token` securely (localStorage, sessionStorage, or cookies)
2. **Token Expiration:** Tokens expire after a certain time. Handle 401 errors by redirecting to login
3. **Token Format:** Always use the format `Bearer <token>` in the Authorization header
4. **Security:** Never expose tokens in URLs or logs

---

## 🗄️ Database Schema Reference

### Preferences Table

```
id          - UUID (auto-generated)
user_id     - UUID (unique, references auth.users)
preference  - TEXT (JSON string)
created_at  - TIMESTAMPTZ
updated_at  - TIMESTAMPTZ
```

### Vote Table

```
id          - UUID (auto-generated)
user_id     - UUID (references auth.users)
song        - TEXT
vote_value  - INT4
vote_time   - TIMESTAMPTZ
```

---

## 📝 Testing with cURL

### Sign Up

```bash
curl -X POST http://localhost:3000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

### Login

```bash
curl -X POST http://localhost:3000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'
```

### Get Preferences

```bash
curl -X GET http://localhost:3000/api/preferences \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### Save Preferences

```bash
curl -X POST http://localhost:3000/api/preferences \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"soundType":"nature","volume":0.75}'
```

### Submit Vote

```bash
curl -X POST http://localhost:3000/api/votes \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"song":"Moonlight Sonata","vote_value":5}'
```

### Get Votes

```bash
curl -X GET http://localhost:3000/api/votes \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

---

## 💡 Tips

1. **Preferences are flexible:** The preference object can have any structure you want
2. **Vote values are integers:** They're automatically converted from strings
3. **User isolation:** Users can only see and modify their own data
4. **Upsert behavior:** POST /api/preferences creates OR updates automatically
5. **Token management:** Implement token refresh logic for better UX

---

## 🆘 Support

If you encounter issues:

1. Check that the server is running (`GET /health`)
2. Verify your token is valid and not expired
3. Check request body format matches examples
4. Look at server logs for detailed error messages
5. Ensure Supabase credentials are correctly configured in `.env`
