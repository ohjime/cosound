# ML Model API Documentation

Base URL: `http://localhost:3000/api/model`

All endpoints require API Key authentication via the `X-API-Key` header.

---

## 🔐 Authentication

All endpoints require the following header:

```
X-API-Key: your-secret-ml-api-key
```

**Configuration:**
Add to your `.env` file:

```env
ML_API_KEY=your-secret-ml-api-key-here
```

---

## 📊 Endpoints

### 1. Get All Users

Retrieve all user profiles.

**Endpoint:** `GET /api/model/users`

**Headers:**

```
X-API-Key: your-secret-ml-api-key
```

**Response (200):**

```json
{
  "success": true,
  "count": 3,
  "data": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "email": "user1@example.com",
      "name": "John Doe",
      "created_at": "2025-11-08T10:00:00.000Z"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "email": "user2@example.com",
      "name": "Jane Smith",
      "created_at": "2025-11-08T11:00:00.000Z"
    }
  ]
}
```

**Error Response (401):**

```json
{
  "error": "Invalid or missing API key"
}
```

---

### 2. Get All Songs

Retrieve a list of all unique songs that have been voted on.

**Endpoint:** `GET /api/model/songs`

**Headers:**

```
X-API-Key: your-secret-ml-api-key
```

**Response (200):**

```json
{
  "success": true,
  "count": 5,
  "data": [
    "Moonlight Sonata",
    "River Flows",
    "Ocean Waves",
    "Forest Ambient",
    "City Sounds"
  ]
}
```

**Use Case:**

- Get the complete catalog of songs in the system
- Build recommendation systems
- Analyze song popularity

---

### 3. Get All Preferences

Retrieve all user preferences with parsed JSON data.

**Endpoint:** `GET /api/model/preferences`

**Headers:**

```
X-API-Key: your-secret-ml-api-key
```

**Response (200):**

```json
{
  "success": true,
  "count": 2,
  "data": [
    {
      "id": "pref-uuid-1",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "preference": {
        "soundType": "nature",
        "volume": 0.75,
        "mood": "calm",
        "tempo": "slow",
        "instruments": ["piano", "ambient"]
      },
      "created_at": "2025-11-08T10:00:00.000Z",
      "updated_at": "2025-11-08T12:00:00.000Z"
    },
    {
      "id": "pref-uuid-2",
      "user_id": "550e8400-e29b-41d4-a716-446655440001",
      "preference": {
        "soundType": "urban",
        "volume": 0.5,
        "mood": "energetic",
        "tempo": "fast",
        "instruments": ["synth", "drums"]
      },
      "created_at": "2025-11-08T11:00:00.000Z",
      "updated_at": "2025-11-08T13:00:00.000Z"
    }
  ]
}
```

**Note:** The `preference` field is automatically parsed from JSON string to object.

**Use Case:**

- Train recommendation models based on user preferences
- Cluster users by similar preferences
- Analyze preference patterns

---

### 4. Get All Votes

Retrieve all votes from all users, ordered by time (newest first).

**Endpoint:** `GET /api/model/votes`

**Headers:**

```
X-API-Key: your-secret-ml-api-key
```

**Response (200):**

```json
{
  "success": true,
  "count": 10,
  "data": [
    {
      "id": "vote-uuid-1",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "song": "Moonlight Sonata",
      "vote_value": 5,
      "vote_time": "2025-11-08T14:30:00.000Z"
    },
    {
      "id": "vote-uuid-2",
      "user_id": "550e8400-e29b-41d4-a716-446655440001",
      "song": "River Flows",
      "vote_value": 4,
      "vote_time": "2025-11-08T14:25:00.000Z"
    },
    {
      "id": "vote-uuid-3",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "song": "Ocean Waves",
      "vote_value": 3,
      "vote_time": "2025-11-08T14:20:00.000Z"
    }
  ]
}
```

**Use Case:**

- Build collaborative filtering models
- Analyze voting patterns over time
- Train rating prediction models
- Generate complete user-item interaction matrix

---

### 5. Get Preferences for a User

Retrieve preferences for a specific user.

**Endpoint:** `GET /api/model/preferences/:userId`

**URL Parameters:**

- `userId` (string, required) - UUID of the user

**Headers:**

```
X-API-Key: your-secret-ml-api-key
```

**Example Request:**

```bash
GET /api/model/preferences/550e8400-e29b-41d4-a716-446655440000
```

**Response (200):**

```json
{
  "success": true,
  "data": {
    "id": "pref-uuid-1",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "preference": {
      "soundType": "nature",
      "volume": 0.75,
      "mood": "calm",
      "tempo": "slow",
      "instruments": ["piano", "ambient"],
      "environmentalSounds": ["rain", "ocean"]
    },
    "created_at": "2025-11-08T10:00:00.000Z",
    "updated_at": "2025-11-08T12:00:00.000Z"
  }
}
```

**Error Response (404):**

```json
{
  "success": false,
  "error": "Preferences not found for this user"
}
```

**Use Case:**

- Get user profile for personalized recommendations
- Feature engineering for user-based models
- Content-based filtering

---

### 6. Get Votes for a User

Retrieve all votes submitted by a specific user.

**Endpoint:** `GET /api/model/votes/:userId`

**URL Parameters:**

- `userId` (string, required) - UUID of the user

**Headers:**

```
X-API-Key: your-secret-ml-api-key
```

**Example Request:**

```bash
GET /api/model/votes/550e8400-e29b-41d4-a716-446655440000
```

**Response (200):**

```json
{
  "success": true,
  "count": 5,
  "data": [
    {
      "id": "vote-uuid-1",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "song": "Moonlight Sonata",
      "vote_value": 5,
      "vote_time": "2025-11-08T14:30:00.000Z"
    },
    {
      "id": "vote-uuid-2",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "song": "Ocean Waves",
      "vote_value": 4,
      "vote_time": "2025-11-08T13:15:00.000Z"
    },
    {
      "id": "vote-uuid-3",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "song": "Forest Ambient",
      "vote_value": 3,
      "vote_time": "2025-11-08T12:00:00.000Z"
    }
  ]
}
```

**Use Case:**

- Analyze individual user voting behavior
- Build user preference vectors
- Identify user's favorite songs
- Generate personalized recommendations

---

### 7. Get All Votes for a Song

Retrieve all votes for a specific song with statistics.

**Endpoint:** `GET /api/model/votes/song/:songName`

**URL Parameters:**

- `songName` (string, required) - Name of the song (URL encoded)

**Headers:**

```
X-API-Key: your-secret-ml-api-key
```

**Example Request:**

```bash
GET /api/model/votes/song/Moonlight%20Sonata
```

**Response (200):**

```json
{
  "success": true,
  "song": "Moonlight Sonata",
  "count": 8,
  "stats": {
    "total_votes": 8,
    "average_vote": 4.25,
    "min_vote": 2,
    "max_vote": 5
  },
  "data": [
    {
      "id": "vote-uuid-1",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "song": "Moonlight Sonata",
      "vote_value": 5,
      "vote_time": "2025-11-08T14:30:00.000Z"
    },
    {
      "id": "vote-uuid-2",
      "user_id": "550e8400-e29b-41d4-a716-446655440001",
      "song": "Moonlight Sonata",
      "vote_value": 4,
      "vote_time": "2025-11-08T14:00:00.000Z"
    },
    {
      "id": "vote-uuid-3",
      "user_id": "550e8400-e29b-41d4-a716-446655440002",
      "song": "Moonlight Sonata",
      "vote_value": 5,
      "vote_time": "2025-11-08T13:30:00.000Z"
    }
  ]
}
```

**Statistics Provided:**

- `total_votes` - Number of votes for this song
- `average_vote` - Mean vote value
- `min_vote` - Minimum vote value
- `max_vote` - Maximum vote value

**Use Case:**

- Analyze song popularity
- Item-based collaborative filtering
- Generate song rankings
- Identify trending songs

---

## 💻 Code Examples

### Python Example

```python
import requests
import json

API_BASE_URL = "http://localhost:3000/api/model"
API_KEY = "your-secret-ml-api-key"

headers = {
    "X-API-Key": API_KEY
}

# Get all votes
response = requests.get(f"{API_BASE_URL}/votes", headers=headers)
votes_data = response.json()
print(f"Total votes: {votes_data['count']}")

# Get all preferences
response = requests.get(f"{API_BASE_URL}/preferences", headers=headers)
preferences_data = response.json()

# Get votes for a specific song
song_name = "Moonlight Sonata"
response = requests.get(
    f"{API_BASE_URL}/votes/song/{song_name}",
    headers=headers
)
song_votes = response.json()
print(f"Average rating for {song_name}: {song_votes['stats']['average_vote']}")

# Get user preferences
user_id = "550e8400-e29b-41d4-a716-446655440000"
response = requests.get(
    f"{API_BASE_URL}/preferences/{user_id}",
    headers=headers
)
user_prefs = response.json()
print(f"User preferences: {user_prefs['data']['preference']}")
```

### JavaScript/Node.js Example

```javascript
const axios = require("axios");

const API_BASE_URL = "http://localhost:3000/api/model";
const API_KEY = "your-secret-ml-api-key";

const headers = {
  "X-API-Key": API_KEY,
};

// Get all votes
async function getAllVotes() {
  const response = await axios.get(`${API_BASE_URL}/votes`, { headers });
  console.log("Total votes:", response.data.count);
  return response.data.data;
}

// Get all preferences
async function getAllPreferences() {
  const response = await axios.get(`${API_BASE_URL}/preferences`, { headers });
  return response.data.data;
}

// Get song statistics
async function getSongStats(songName) {
  const response = await axios.get(
    `${API_BASE_URL}/votes/song/${encodeURIComponent(songName)}`,
    { headers }
  );
  return response.data.stats;
}

// Get user voting history
async function getUserVotes(userId) {
  const response = await axios.get(`${API_BASE_URL}/votes/${userId}`, {
    headers,
  });
  return response.data.data;
}

// Usage
(async () => {
  const votes = await getAllVotes();
  const preferences = await getAllPreferences();
  const songStats = await getSongStats("Moonlight Sonata");
  console.log("Song stats:", songStats);
})();
```

### cURL Examples

```bash
# Get all users
curl -X GET http://localhost:3000/api/model/users \
  -H "X-API-Key: your-secret-ml-api-key"

# Get all songs
curl -X GET http://localhost:3000/api/model/songs \
  -H "X-API-Key: your-secret-ml-api-key"

# Get all preferences
curl -X GET http://localhost:3000/api/model/preferences \
  -H "X-API-Key: your-secret-ml-api-key"

# Get all votes
curl -X GET http://localhost:3000/api/model/votes \
  -H "X-API-Key: your-secret-ml-api-key"

# Get preferences for a user
curl -X GET http://localhost:3000/api/model/preferences/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your-secret-ml-api-key"

# Get votes for a user
curl -X GET http://localhost:3000/api/model/votes/550e8400-e29b-41d4-a716-446655440000 \
  -H "X-API-Key: your-secret-ml-api-key"

# Get all votes for a song
curl -X GET http://localhost:3000/api/model/votes/song/Moonlight%20Sonata \
  -H "X-API-Key: your-secret-ml-api-key"
```

---

## 🎯 Common ML Use Cases

### 1. Collaborative Filtering

```python
# Get all votes to build user-item matrix
response = requests.get(f"{API_BASE_URL}/votes", headers=headers)
votes = response.json()['data']

# Create user-item matrix
import pandas as pd
df = pd.DataFrame(votes)
user_item_matrix = df.pivot_table(
    index='user_id',
    columns='song',
    values='vote_value'
)
```

### 2. Content-Based Filtering

```python
# Get user preferences and voting history
user_id = "user-uuid"
prefs = requests.get(f"{API_BASE_URL}/preferences/{user_id}", headers=headers).json()
votes = requests.get(f"{API_BASE_URL}/votes/{user_id}", headers=headers).json()

# Extract features
user_features = prefs['data']['preference']
user_ratings = votes['data']

# Build content-based model
# ... your ML model code
```

### 3. Trend Analysis

```python
# Get all songs and their statistics
songs = requests.get(f"{API_BASE_URL}/songs", headers=headers).json()['data']

trending_songs = []
for song in songs:
    stats = requests.get(
        f"{API_BASE_URL}/votes/song/{song}",
        headers=headers
    ).json()['stats']

    trending_songs.append({
        'song': song,
        'avg_rating': stats['average_vote'],
        'total_votes': stats['total_votes']
    })

# Sort by popularity
trending_songs.sort(key=lambda x: x['total_votes'], reverse=True)
```

### 4. Personalized Recommendations

```python
# Get user preferences
user_id = "user-uuid"
user_prefs = requests.get(
    f"{API_BASE_URL}/preferences/{user_id}",
    headers=headers
).json()['data']

# Get all songs
all_songs = requests.get(f"{API_BASE_URL}/songs", headers=headers).json()['data']

# Get user's voting history
user_votes = requests.get(
    f"{API_BASE_URL}/votes/{user_id}",
    headers=headers
).json()['data']

already_voted = [v['song'] for v in user_votes]

# Filter songs user hasn't voted on
recommendations = [s for s in all_songs if s not in already_voted]

# Score recommendations based on user preferences
# ... your recommendation algorithm
```

---

## 🔒 Security Notes

1. **API Key Protection:**

   - Never expose API key in client-side code
   - Store in environment variables
   - Rotate keys regularly
   - Use different keys for dev/prod

2. **Rate Limiting:**

   - Consider implementing rate limits for production
   - Monitor API usage

3. **Data Privacy:**
   - Ensure compliance with data protection regulations
   - Consider anonymizing user IDs when possible
   - Log access for audit purposes

---

## 📊 Response Format

All successful responses follow this structure:

```json
{
  "success": true,
  "count": 10,        // Optional: number of items
  "data": [...],      // Array or object with the data
  "stats": {...}      // Optional: statistics (for song votes)
}
```

All error responses:

```json
{
  "error": "Error message description"
}
```

---

## ⚠️ Error Codes

- `401` - Invalid or missing API key
- `404` - Resource not found (user preferences, etc.)
- `400` - Bad request (database error)
- `500` - Internal server error

---

## 🚀 Quick Start

1. **Set up environment:**

   ```env
   ML_API_KEY=your-secret-key-here
   ```

2. **Test connection:**

   ```bash
   curl -X GET http://localhost:3000/api/model/songs \
     -H "X-API-Key: your-secret-key-here"
   ```

3. **Start building your model:**

   ```python
   import requests

   API_KEY = "your-secret-key-here"
   headers = {"X-API-Key": API_KEY}

   # Fetch training data
   votes = requests.get(
       "http://localhost:3000/api/model/votes",
       headers=headers
   ).json()['data']

   # Build your model...
   ```

---

## 📞 Support

For issues or questions:

- Check server logs for detailed error messages
- Verify API key is set correctly in `.env`
- Ensure Supabase credentials are configured
- Check that required tables exist in database
