# 🎧 CoSounds - Adaptive, Personalized, Collaborative Soundscapes. 
<img width="1700" height="946" alt="image" src="https://github.com/user-attachments/assets/c2138197-d27c-4177-b33f-9ac8a2503a54" />

 [natHacks 2025](https://drive.google.com/file/d/10n1oRwq8HrAsufm21Z_m6vwvh6lPTaxH/view?usp=sharing) • [Slidedoc](https://drive.google.com/file/d/1nI1k9LKL2yyn4SobaTB9S7pXkTnIi14_/view?usp=sharing) • [Video](https://drive.google.com/file/d/1CbsY1Lxtr8HvMyOpir7ImNoL-SS7RI9B/view?usp=sharing) 

## 🌱 Inspiration
Stress is something we can all relate to, and music is a universal way to relax.

Dr. Michael Frishkopf's Mindful Listening Spaces at the Cameron Library aimed to bring students together through shared ambient soundscapes. However, participation remained low — students rarely interacted with the system, limiting its ability to adapt to collective preferences.

Our team was inspired to solve this by making interaction seamless, non-intrusive, and meaningful. We asked ourselves:

- How can we get students to participate effortlessly?
- Can we identify users without forcing sign-ups?
- How can the system stay ethical and preserve privacy?

Co-sounds is our answer — a blend of AI, sound, and interaction design that lets students co-create adaptive, mindful soundscapes together.

## 🎶 What It Does

Co-sounds transforms passive listening into a collaborative, responsive experience.

Students simply tap their phones on an NFC tag to:

- Submit quick preferences or votes on the current soundscape
- Provide feedback on relaxation and focus levels
- Seamlessly contribute to a collective mood model

The system uses this data to generate adaptive soundscapes that reflect both individual and group preferences, helping students relax and connect in shared spaces.

## 🏗️ How We Built It

### Architecture

Co-sounds consists of three integrated components:

### 1. 🌐 Web Application

- React-based responsive interface
- Real-time voting and feedback system
- NFC tag support for tap-based interaction
- Supabase authentication and data storage
- Music preference surveys and user settings
- Vote confirmation animations and progress indicators

### 2. 🖥️ Backend Server

- Express.js REST API
- Secure integration with Supabase
- JWT authentication and API key protection
- Real-time session management for collective soundscapes

### 3. 🧠 Machine Learning Model

- Built with a Linear Ridge Regression classifier
- Trained on the ESC-50 dataset (Environmental Sound Classification)
- Generates audio feature embeddings used to match user preferences to songs
- Produces both individual and collective recommendation vectors

## ⚙️ Challenges We Ran Into

- Designing an interaction flow that was low-effort but engaging
- Balancing anonymity with persistent user identification
- Training a sound classification model from raw audio using mathematical feature extraction and regression techniques
- Integrating physical NFC inputs with digital web services
- Ensuring reliable real-time feedback loops between frontend, backend, and ML model

## 🏅 Accomplishments That We're Proud Of

- Successfully built a working prototype that connects NFC inputs to an adaptive ML pipeline
- Developed a linear ridge regression model that classifies soundscapes using ESC-50 data
- Created a learning algorithm that evolves based on user feedback and collective trends

## 💡 What We Learned

- The power of user-centered design in encouraging participation
- How to bridge physical interactions (NFC) with cloud-based AI systems
- The importance of ethical data collection and minimizing intrusiveness
- How small design choices (like frictionless taps) can dramatically increase engagement

## 🚀 What's Next for Co-sounds

- Deploying Co-sounds in the Cameron Library Mindful Listening Space for pilot testing
- Expanding the ML system to learn from emotion recognition
- Building a mobile app companion for personalized profiles and real-time analytics
- Introducing new sound categories and generative audio synthesis for richer ambient experiences

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

---

**Happy Voting! 🎵👍👎**
