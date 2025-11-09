const express = require('express');
const cors = require('cors');
require('dotenv').config();
const authRoutes = require("./routes/auth.js");
const prefVoteRoutes = require("./routes/prefVote.js");
const modelRoutes = require("./routes/modelRoutes.js");

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(cors());
app.use(express.json());

app.use("/api/auth", authRoutes);
app.use("/api", prefVoteRoutes);
app.use("/api/model", modelRoutes);
app.get("/health", (req, res) => {
  res.json({ status: "ok", timestamp: new Date().toISOString() });
});
app.use((req, res) => {
  res.status(404).json({ error: "Route not found" });
});
app.listen(PORT, () => console.log(`Server running on http://localhost:${PORT}`));
