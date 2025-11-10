
// src/server/index.js
const path = require("path");
// ✅ Load .env from project root
require("dotenv").config({ path: path.join(__dirname, "../.env") });

// sanity check (remove after)
["SUPABASE_URL","SUPABASE_ANON_KEY"].forEach(k=>{
  if(!process.env[k]) { console.error(`Missing ${k}`); process.exit(1); }
});

const express = require('express');
const cors = require('cors');


// require('dotenv').config();
const { createClient } = require("@supabase/supabase-js");

const authRoutes = require("./routes/auth.js");
const prefVoteRoutes = require("./routes/prefVote.js");
const modelRoutes = require("./routes/modelRoutes.js");
const leaderboardRoutes = require("./routes/leaderboard.js");
const sessionRoutes = require("./routes/session.js");

const app = express();
const PORT = process.env.PORT || 3000;

const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_ANON_KEY // or SERVICE_ROLE_KEY if you need admin privileges
);


app.use((req, res, next) => {
  req.supabase = supabase;
  next();
});

// Middleware
app.use(cors());
app.use(express.json());

app.use("/api/auth", authRoutes);
app.use("/api", prefVoteRoutes);
app.use("/api", sessionRoutes);
app.use("/api/model", modelRoutes);
app.use("/api/leaderboard", leaderboardRoutes);
app.get("/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});
app.use((req, res) => {
  res.status(404).json({ error: "Route not found" });
});
app.listen(PORT, () => console.log(`Server running on http://localhost:${PORT}`));
