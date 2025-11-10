const express = require('express');
const router = express.Router();
const { createClient } = require('@supabase/supabase-js');
const authenticateApiKey = require('../middleware/authenticateApiKey');

// // Initialize Supabase client
// const supabase = createClient(
//   process.env.SUPABASE_URL,
//   process.env.SUPABASE_ANON_KEY
// );

// All routes protected by API key authentication
// router.use(authenticateApiKey);

// ============================================
// MODEL DATA ENDPOINTS
// ============================================

/**
 * GET /api/model/users
 * Get all users
 */
router.get('/users', async (req, res) => {
  try {
    const { data, error } = await req.supabase
      .from('profiles')
      .select('*');

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    res.status(200).json({
      success: true,
      count: data.length,
      data,
    });
  } catch (err) {
    console.error('Get users error:', err);
    res.status(500).json({ error: 'Failed to fetch users' });
  }
});

/**
 * GET /api/model/songs
 * Get all unique songs from votes
 */
router.get('/songs', async (req, res) => {
  try {
    const { data, error } = await supabase
      .from('vote')
      .select('song')
      .order('song');

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    // Get unique songs
    const uniqueSongs = [...new Set(data.map(v => v.song))];

    res.status(200).json({
      success: true,
      count: uniqueSongs.length,
      data: uniqueSongs,
    });
  } catch (err) {
    console.error('Get songs error:', err);
    res.status(500).json({ error: 'Failed to fetch songs' });
  }
});

/**
 * GET /api/model/preferences
 * Get all user preferences
 */
router.get('/preferences', async (req, res) => {
  try {
    const { data, error } = await supabase
      .from('preferences')
      .select('*');

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    // Parse preference JSON strings
    const parsedData = data.map(pref => ({
      ...pref,
      preference: JSON.parse(pref.preference),
    }));

    res.status(200).json({
      success: true,
      count: parsedData.length,
      data: parsedData,
    });
  } catch (err) {
    console.error('Get preferences error:', err);
    res.status(500).json({ error: 'Failed to fetch preferences' });
  }
});

/**
 * GET /api/model/active-users
 * Get all currently active users (with unexpired sessions)
 * Returns user preferences for music selection algorithm
 */
router.get('/active-users', async (req, res) => {
  try {
    const now = new Date().toISOString();
    
    // Get all active, unexpired sessions
    const { data: sessions, error } = await supabase
      .from('sessions')
      .select(`
        user_id,
        checked_in_at,
        expires_at,
        profiles!inner(display_name, name)
      `)
      .eq('status', 'active')
      .gt('expires_at', now); // Only non-expired sessions
    
    if (error) {
      return res.status(400).json({ error: error.message });
    }
    
    // Get preferences for each active user
    const activeUsers = await Promise.all(
      sessions.map(async (session) => {
        const { data: prefs } = await supabase
          .from('preferences')
          .select('preference')
          .eq('user_id', session.user_id)
          .single();
        
        return {
          user_id: session.user_id,
          display_name: session.profiles.display_name || 
                       session.profiles.name?.split(' ')[0] || 
                       'Anonymous',
          checked_in_at: session.checked_in_at,
          expires_at: session.expires_at,
          preferences: prefs ? JSON.parse(prefs.preference) : [0, 0, 0, 0, 0]
        };
      })
    );
    
    res.json({
      success: true,
      count: activeUsers.length,
      timestamp: now,
      data: activeUsers
    });
  } catch (err) {
    console.error('Get active users error:', err);
    res.status(500).json({ error: 'Failed to get active users' });
  }
});

/**
 * GET /api/model/votes
 * Get all votes
 */
router.get('/votes', async (req, res) => {
  try {
    const { data, error } = await supabase
      .from('vote')
      .select('*')
      .order('vote_time', { ascending: false });

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    res.status(200).json({
      success: true,
      count: data.length,
      data,
    });
  } catch (err) {
    console.error('Get votes error:', err);
    res.status(500).json({ error: 'Failed to fetch votes' });
  }
});

/**
 * GET /api/model/preferences/:userId
 * Get preferences for a specific user
 */
router.get('/preferences/:userId', async (req, res) => {
  try {
    const { userId } = req.params;

    const { data, error } = await supabase
      .from('preferences')
      .select('*')
      .eq('user_id', userId)
      .single();

    if (error && error.code !== 'PGRST116') {
      return res.status(400).json({ error: error.message });
    }

    if (!data) {
      return res.status(404).json({ 
        success: false,
        error: 'Preferences not found for this user' 
      });
    }

    // Parse preference JSON string
    const parsedData = {
      ...data,
      preference: JSON.parse(data.preference),
    };

    res.status(200).json({
      success: true,
      data: parsedData,
    });
  } catch (err) {
    console.error('Get user preferences error:', err);
    res.status(500).json({ error: 'Failed to fetch user preferences' });
  }
});

/**
 * GET /api/model/votes/:userId
 * Get all votes for a specific user
 */
router.get('/votes/:userId', async (req, res) => {
  try {
    const { userId } = req.params;

    const { data, error } = await supabase
      .from('vote')
      .select('*')
      .eq('user_id', userId)
      .order('vote_time', { ascending: false });

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    res.status(200).json({
      success: true,
      count: data.length,
      data,
    });
  } catch (err) {
    console.error('Get user votes error:', err);
    res.status(500).json({ error: 'Failed to fetch user votes' });
  }
});

/**
 * GET /api/model/votes/song/:songName
 * Get all votes for a specific song
 */
router.get('/votes/song/:songName', async (req, res) => {
  try {
    const { songName } = req.params;

    const { data, error } = await supabase
      .from('vote')
      .select('*')
      .eq('song', songName)
      .order('vote_time', { ascending: false });

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    // Calculate statistics
    const stats = {
      total_votes: data.length,
      average_vote: data.length > 0 
        ? data.reduce((sum, v) => sum + v.vote_value, 0) / data.length 
        : 0,
      min_vote: data.length > 0 ? Math.min(...data.map(v => v.vote_value)) : 0,
      max_vote: data.length > 0 ? Math.max(...data.map(v => v.vote_value)) : 0,
    };

    res.status(200).json({
      success: true,
      song: songName,
      count: data.length,
      stats,
      data,
    });
  } catch (err) {
    console.error('Get song votes error:', err);
    res.status(500).json({ error: 'Failed to fetch song votes' });
  }
});




function parsePgvectorString(s) {
  return String(s)
    .trim()
    .replace(/^[\[\(]\s*/, "")   // drop leading [ or (
    .replace(/[\]\)]\s*$/, "")   // drop trailing ] or )
    .split(",")
    .map(t => Number(t.trim()))
    .filter(Number.isFinite);
}

/**
 * GET /api/model/recommend?limit=5
 * Uses active sessions' users; if none, uses all users in preferences.
 */
router.get("/recommend", async (req, res) => {
  try {
    // const limit = Number(req.query.limit) || 5;

    // // 1) Active users from sessions
    // const { data: activeSessions, error: sessErr } = await req.supabase
    //   .from("sessions")
    //   .select("user_id")
    //   .eq("status", "active");

    // if (sessErr) {
    //   console.error("sessions query error:", sessErr);
    //   return res.status(500).json({ error: "Failed to read active users" });
    // }

    // let userIds = (activeSessions || []).map(r => r.user_id).filter(Boolean);
    // console.log("Active user IDs from sessions:", userIds);

    // // 2) Fallback: all users who have a preference
    // if (userIds.length === 0) {
    //   const { data: allPrefs, error: allErr } = await req.supabase
    //     .from("preferences")
    //     .select("user_id");

    //   if (allErr) {
    //     console.error("preferences fallback error:", allErr);
    //     return res.status(500).json({ error: "Failed to read preferences" });
    //   }

    //   userIds = (allPrefs || []).map(r => r.user_id).filter(Boolean);
    // }

    const { data: allPrefs, error: allErr } = await req.supabase
      .from("preferences")
      .select("user_id");

    if (allErr) {
      console.error("preferences fallback error:", allErr);
      return res.status(500).json({ error: "Failed to read preferences" });
    }

    userIds = (allPrefs || []).map(r => r.user_id).filter(Boolean);    

    // dedupe & guard
    userIds = [...new Set(userIds)];
    if (userIds.length === 0) {
      return res.status(404).json({ error: "No users available to compute group preference" });
    }

    console.log("Using user IDs for recommendation:", userIds);

    // 3) Fetch their preference vectors (pgvector)
    const { data: prefs, error: prefErr } = await req.supabase
      .from("preferences")
      .select("user_id, preference")
      .in("user_id", userIds);

    if (prefErr) {
      console.error("preferences query error:", prefErr);
      return res.status(500).json({ error: "Failed to fetch user preferences" });
    }
    if (!prefs?.length) {
      return res.status(404).json({ error: "No preferences found for selected users" });
    }

    console.log(prefs);
    // 4) Parse vectors and compute mean (then normalize for cosine)
    const vectors = prefs
      .map(r => parsePgvectorString(r.preference))
      .filter(v => v.length > 0);

    if (!vectors.length) return res.status(422).json({ error: "No valid vectors in preferences" });

    console.log(vectors);

    const d = vectors[0].length;
    const sum = Array(d).fill(0);
    for (const v of vectors) for (let i = 0; i < d; i++) sum[i] += v[i];
    const mean = sum.map(x => x / vectors.length);

    const norm = Math.hypot(...mean);
    const meanUnit = norm ? mean.map(x => x / norm) : mean;

    // 5) Cosine similarity search against songs (simple & reliable)
    const vecText = `[${meanUnit.join(",")}]`;

    const { data: recs, error: rpcErr } = await req.supabase.rpc(
      "recommend_with_penalty",
      { p_vec: vecText, p_limit: 1 }
    );
    if (rpcErr) return res.status(500).json({ error: "Failed to fetch recommendations" });

    res.status(200).json({
      success: true,
      user_count: userIds.length,
      users_used: userIds,
      mean_vector: meanUnit,
      recommendations: recs,
    });
    
  } catch (err) {
    console.error('Recommendation error:', err);
    res.status(500).json({ error: 'Failed to generate recommendations' });
  }
});


router.post("/currentSong", async (req, res) => {
  try {
    const { song_title } = req.body;

    // Validate input
    if (!song_title) {
      return res.status(400).json({ error: "song_title is required" });
    }

    // Insert into songs_playing
    const { data, error } = await req.supabase
      .from("songs_playing")
      .insert([{ song_title }])
      .select()
      .single();

    if (error) {
      console.error("Error inserting song_playing:", error);
      return res.status(500).json({ error: "Failed to log current song" });
    }

        // 2) Update last_played on the matching song
    const { data: song, error: updateErr } = await req.supabase
      .from("songs")
      .update({ last_played: new Date().toISOString() })
      .eq("title", song_title)
      .select("id,title,last_played")
      .single(); // use .single() if title is unique

    if (updateErr) {
      console.error("Error updating last_played:", updateErr);
      return res.status(500).json({ error: "Logged play, but failed to update last_played" });
    }

    res.status(201).json({
      success: true,
      message: "Current song logged and last_played updated",
      data: { playing: data, song },
    });
  } catch (err) {
    console.error("currentSong error:", err);
    res.status(500).json({ error: "Internal server error" });
  }
});


router.get("/currentSong", async (req, res) => {
  try {
    // Fetch the most recent song from songs_playing
    const { data, error } = await req.supabase
      .from("songs_playing")
      .select("song_title, played_at")
      .order("played_at", { ascending: false })
      .limit(1)
      .single();

    if (error) {
      console.error("Error fetching current song:", error);
      return res.status(500).json({ error: "Failed to fetch current song" });
    }

    if (!data) {
      return res.status(404).json({ error: "No songs have been played yet" });
    }

    res.status(200).json({
      success: true,
      current_song: data.song_title,
      played_at: data.played_at,
    });
  } catch (err) {
    console.error("currentSong (GET) error:", err);
    res.status(500).json({ error: "Internal server error" });
  }
});

module.exports = router;
