# 🎵 Cosound - Interactive Music Voting Platform

A real-time music voting and recommendation system that allows users to vote on songs using NFC tags or web interface, while capturing user preferences to deliver a collective personalized music recommendations.

## 🎯 What Is This?

**Cosound** is an interactive music engagement platform designed for social listening experiences. It combines:

- **Real-time Voting**: Vote on currently playing songs via NFC tags or web interface
- **Preference Learning**: Collect user music preferences through an intuitive survey
- **Smart Recommendations**: Generate personalized song recommendations based on collective preferences
- **Leaderboard System**: Track top-rated songs and user engagement
- **Session Management**: Manage listening rooms and user participation

## 🏗️ Architecture

The project consists of three main components:

### 1. **Web Application** (`src/web/`)

- React-based responsive web interface
- Real-time voting interface with NFC tag support
- User authentication via Supabase
- Music preference survey system
- Vote confirmation animations
- User settings and profile management

### 2. **Backend Server** (`src/server/`)

- Express.js REST API
- Supabase integration for data persistence
- JWT authentication
- API key protection for model endpoints
- Real-time session management

### 3. **Machine Learning Model** (`ml_model`)

#### What It Does

The ML model classifies audio into 5 environmental sound categories:

1. **Rain** 🌧️
2. **Sea Waves** 🌊
3. **Thunderstorm** ⛈️
4. **Wind** 💨
5. **Crackling Fire** 🔥

User preferences are collected for these 5 categories (values 0-1), which the system uses to recommend songs with matching ambient characteristics.

#### How It Works

- **Dataset**: Uses the ESC-50 dataset (Environmental Sound Classification - 50 categories)
- **Model**: Linear Ridge Regression classifier
- **Input**: Audio files (.wav format)
- **Output**: Classification scores for each of the 5 sound categories
- **Integration**: User preference vectors are matched against song audio profiles

## 🚀 Getting Started

#### 1. Clone the repository

```bash
git clone https://github.com/ohjime/soundguys.git
cd soundguys
```

#### 2. Install Backend Server Dependencies

```bash
cd src/server
npm install
```

#### 3. Install Web Application Dependencies

```bash
cd ../web
npm install
```

#### 4. Install ML Model Dependencies

```bash
cd ../../ml_model
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### Environment Setup

#### 📝 Server Environment Variables

Create `src/server/.env`:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Server Configuration
PORT=3000

# API Security (choose a strong random string)
API_KEY=your_secret_api_key_here
```

2. **API_KEY**:
   - Generate a random secure string (e.g., using `openssl rand -hex 32`)
   - This protects the ML model endpoints from unauthorized access

#### 📝 Web Environment Variables

Create `src/web/.env`:

```env
# Supabase Configuration (same as server)
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
VITE_API_URL=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=
OPEN_API_KEY=

# Backend API URL
VITE_API_BASE_URL=http://localhost:3000
```

**Note:** Use the same Supabase URL and anon key as the server. The `VITE_` prefix is required for Vite to expose these to the browser.

## 🎮 Running the Application

### Start the Backend Server

```bash
cd src/server
npm start
# Or for development with auto-reload:
npm run dev
```

Server will run on `http://localhost:3000`

**Verify it's working:** Visit `http://localhost:3000/health`

```json
{
  "status": "ok",
  "timestamp": "2025-11-10T..."
}
```

### Start the Web Application

In a new terminal:

```bash
cd src/web
npm run dev
```

Web app will run on `http://localhost:5173` (Vite default)

## 🛠️ Technology Stack

**Frontend:**

- React 19
- React Router DOM
- TailwindCSS 4
- Vite 7
- Jotai (state management)
- Lucide React (icons)

**Backend:**

- Node.js
- Express 5
- Supabase (PostgreSQL + Auth)
- JWT Authentication
- CORS

**Machine Learning:**

- Python 3.8+
- Librosa (audio processing)
- Scikit-learn (Ridge Regression)
- NumPy & SciPy
- ESC-50 Dataset

## 📚 Documentation

- `docs/API_DOCUMENTATION.md` - Complete REST API reference
- `docs/MODEL_API_DOCUMENTATION.md` - ML endpoints documentation
- `ml_model/README.md` - ML model details & training guide

**Happy Voting! 🎵👍👎**
