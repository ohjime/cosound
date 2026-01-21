const express = require('express');
const router = express.Router();
const { createClient } = require('@supabase/supabase-js');
const { authenticateToken } = require('../middleware/auth');

const serviceClient = process.env.SUPABASE_SERVICE_ROLE_KEY
  ? createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY)
  : null;

// ============================================
// PREFERENCE ENDPOINTS (Protected)
// ============================================

/**
 * GET /api/preferences
 * Get user's preferences
 */
router.get('/preferences', authenticateToken, async (req, res) => {
  try {
    const { data, error } = await req.supabase
      .from('preferences')
      .select('*')
      .eq('user_id', req.user.id)
      .single();
    
    if (error && error.code !== 'PGRST116') {
      return res.status(400).json({ error: error.message });
    }
    
    if (!data) {
      // No preferences yet, return defaults
      return res.json({
        success: true,
        data: {
          user_id: req.user.id,
          preference: [0, 0, 0, 0, 0] // Default: all 0
        }
      });
    }
    
    res.json({
      success: true,
      data: {
        ...data,
        preference: JSON.parse(data.preference) // Parse JSON string to array
      }
    });
  } catch (err) {
    console.error('Get preferences error:', err);
    res.status(500).json({ error: 'Failed to get preferences' });
  }
});

/**
 * POST /api/preferences
 * Create or update user's preferences
 * Body: JSON object as Array [0.5, 0.8, 0.2, 1.0, 0.0]
 */
// POST /api/preferences
router.post('/preferences', authenticateToken, async (req, res) => {
  try {
    const { preferences } = req.body
    
    // Validate array
    if (!Array.isArray(preferences) || preferences.length !== 5) {
      return res.status(400).json({ 
        error: 'Preferences must be an array of 5 numbers' 
      });
    }
    
    // Validate each value is 0-1
    const allValid = preferences.every(v => 
      typeof v === 'number' && v >= 0 && v <= 1
    );
    
    if (!allValid) {
      return res.status(400).json({ 
        error: 'Each preference must be a number between 0 and 1' 
      });
    }
    
    // Check if preferences already exist
    const { data: existing } = await req.supabase
      .from('preferences')
      .select('*')
      .eq('user_id', req.user.id)
      .single();
    
    let data, error;
    
    if (existing) {
      // Update existing preferences
      const result = await req.supabase
        .from('preferences')
        .update({
          preference: JSON.stringify(preferences)
        })
        .eq('user_id', req.user.id)
        .select()
        .single();
      
      data = result.data;
      error = result.error;
    } else {
      // Insert new preferences
      const result = await req.supabase
        .from('preferences')
        .insert({
          user_id: req.user.id,
          preference: JSON.stringify(preferences)
        })
        .select()
        .single();
      
      data = result.data;
      error = result.error;
    }
    
    if (error) {
      return res.status(400).json({ error: error.message });
    }
    
    res.json({
      success: true,
      data: {
        ...data,
        preference: JSON.parse(data.preference) // Return as array
      }
    });
  } catch (err) {
    console.error('Save preferences error:', err);
    res.status(500).json({ error: 'Failed to save preferences' });
  }
});

// ============================================
// VOTE ENDPOINTS (Protected)
// ============================================

/**
 * GET /api/votes
 * Get user's votes
 * Query params (optional): ?song=songname
 */
router.get('/votes', authenticateToken, async (req, res) => {
  try {
    let query = req.supabase
      .from('vote')
      .select('*')
      .eq('user_id', req.user.id);

    // Optional: Filter by song if provided in query params
    if (req.query.song) {
      query = query.eq('song', req.query.song);
    }

    const { data, error } = await query;

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    res.status(200).json({
      success: true,
      data,
    });
  } catch (err) {
    console.error('Get votes error:', err);
    res.status(500).json({ error: 'Failed to fetch votes' });
  }
});


// ---------- helpers ----------
function parsePgVector(s) {
  return String(s)
    .trim()
    .replace(/^[\[\(]\s*/, "")
    .replace(/[\]\)]\s*$/, "")
    .split(",")
    .map(t => Number(t.trim()))
    .filter(Number.isFinite);
}
const dot = (a, b) => a.reduce((acc, x, i) => acc + x * b[i], 0);
const norm = v => Math.hypot(...v);
const normalize = v => {
  const n = norm(v);
  return n > 0 ? v.map(x => x / n) : v;
};
const toPgVector = v => `[${v.join(",")}]`;



// /**
//  * POST /api/votes/apply
//  * Body: { song_title: string, vote_value: 1 | -1, user_id?: uuid }
//  * If you have auth middleware, prefer req.user.id over body.user_id.
//  */
// router.post("/votes/apply", async (req, res) => {
//   try {
//     const userId = req.user?.id || req.body.user_id;
//     const { song_title, vote_value } = req.body;

//     if (!userId) return res.status(400).json({ error: "user_id required" });
//     if (!song_title) return res.status(400).json({ error: "song_title required" });
//     if (![1, -1].includes(vote_value)) {
//       return res.status(400).json({ error: "vote_value must be 1 or -1" });
//     }

//     // 1) Fetch song embedding (vector(5))
//     const { data: song, error: songErr } = await req.supabase
//       .from("songs")
//       .select("embedding")
//       .eq("title", song_title)
//       .single();
//     if (songErr || !song) return res.status(404).json({ error: "Song not found" });

//     console.log("Song embedding:", parsePgVector(song.embedding));
//     let s = normalize(parsePgVector(song.embedding));
//     if (s.length !== 5) return res.status(422).json({ error: "Song vector not 5D" });

//     // 2) Fetch current user preference (vector(5)) or cold start
//     const { data: prefRow, error: prefErr } = await req.supabase
//       .from("preferences")
//       .select("preference")
//       .eq("user_id", userId)
//       .single();

//     let u;
//     if (prefErr && prefErr.code !== "PGRST116") {
//       return res.status(500).json({ error: "Failed to load user preference" });
//     }
//     if (!prefRow) {
//       // Cold start: on like, start at song; on dislike, use a neutral prior
//       u = vote_value === 1 ? s.slice() : normalize([1, 0, 0, 0, 0]);
//     } else {
//       u = normalize(parsePgVector(prefRow.preference));
//       if (u.length !== 5) return res.status(422).json({ error: "User vector not 5D" });
//     }
//     console.log("PrefRow:", prefRow);
//     console.log("User vector (u):", u);
//     console.log("Song vector (s):", s);
//     // 3) Compute similarity and choose params
//     const sim = dot(u, s); // cosine in [-1,1]
//     const alpha = 0.12;    // learning rate
//     const beta = 0.7;      // dislike softness

//     // 4) Apply update
//     let uPrime;
//     if (vote_value === 1) {
//       // Like: u' = normalize( (1-α)u + α s )
//       uPrime = normalize(u.map((ui, i) => (1 - alpha) * ui + alpha * s[i]));
//     } else {
//       // Dislike: u' = normalize( u - α β (u·s) s )
//       uPrime = normalize(u.map((ui, i) => ui - alpha * beta * sim * s[i]));
//     }

//     console.log("Updated user vector (u'):", uPrime);
//     console.log("PG vector format:", toPgVector(uPrime));

//     // 5) Save updated preference
//     const { data: savedPref, error: upErr } = await req.supabase
//       .from("preferences")
//       .upsert(
//         {
//           user_id: userId,
//           preference: toPgVector(uPrime),
//           updated_at: new Date().toISOString()
//         },
//         { onConflict: "user_id" }
//       )
//       .select()
//       .single();
//     if (upErr) return res.status(500).json({ error: "Failed to save updated preference", details: upErr.message });

//     // 6) (Optional) Record the vote event
//     // await req.supabase.from("vote").insert({ user_id: userId, song: song_title, vote_value });

//     return res.status(200).json({
//       success: true,
//       params_used: { alpha, beta },
//       similarity_before: sim,
//       preference_before: u,
//       preference_after: uPrime,
//       saved: savedPref
//     });
//   } catch (e) {
//     console.error("apply vote error:", e);
//     return res.status(500).json({ error: "Internal server error" });
//   }
// });




/**
 * POST /api/votes
 * Create a new vote
 * Body: { song: string, vote_value: number }
 */
router.post('/votes', authenticateToken, async (req, res) => {
  try {
    const userId = req.user?.id || req.body.user_id;
    const song_title = req.body.song;
    const vote_value = req.body.vote_value;

    // Validate required fields
    if (!song_title || vote_value === undefined) {
      return res.status(400).json({ 
        error: 'Song and vote_value are required' 
      });
    }

    if (!userId) return res.status(400).json({ error: "user_id required" });
    if (!song_title) return res.status(400).json({ error: "song_title required" });
    if (![1, -1].includes(vote_value)) {
      return res.status(400).json({ error: "vote_value must be 1 or -1" });
    }

    // 1) Fetch song embedding (vector(5))
    const { data: song, error: songErr } = await req.supabase
      .from("songs")
      .select("embedding")
      .eq("title", song_title)
      .single();
    if (songErr || !song) return res.status(404).json({ error: "Song not found" });

    console.log("Song embedding:", parsePgVector(song.embedding));
    let s = normalize(parsePgVector(song.embedding));
    if (s.length !== 5) return res.status(422).json({ error: "Song vector not 5D" });

    // 2) Fetch current user preference (vector(5)) or cold start
    const { data: prefRow, error: prefErr } = await req.supabase
      .from("preferences")
      .select("preference")
      .eq("user_id", userId)
      .single();

    let u;
    if (prefErr && prefErr.code !== "PGRST116") {
      return res.status(500).json({ error: "Failed to load user preference" });
    }
    if (!prefRow) {
      // Cold start: on like, start at song; on dislike, use a neutral prior
      u = vote_value === 1 ? s.slice() : normalize([1, 0, 0, 0, 0]);
    } else {
      u = normalize(parsePgVector(prefRow.preference));
      if (u.length !== 5) return res.status(422).json({ error: "User vector not 5D" });
    }
    console.log("PrefRow:", prefRow);
    console.log("User vector (u):", u);
    console.log("Song vector (s):", s);
    // 3) Compute similarity and choose params
    const sim = dot(u, s); // cosine in [-1,1]
    const alpha = 0.12;    // learning rate
    const beta = 0.7;      // dislike softness

    // 4) Apply update
    let uPrime;
    if (vote_value === 1) {
      // Like: u' = normalize( (1-α)u + α s )
      uPrime = normalize(u.map((ui, i) => (1 - alpha) * ui + alpha * s[i]));
    } else {
      // Dislike: u' = normalize( u - α β (u·s) s )
      uPrime = normalize(u.map((ui, i) => ui - alpha * beta * sim * s[i]));
    }

    console.log("Updated user vector (u'):", uPrime);
    console.log("PG vector format:", toPgVector(uPrime));

    // 5) Save updated preference
    const { data: savedPref, error: upErr } = await req.supabase
      .from("preferences")
      .upsert(
        {
          user_id: userId,
          preference: toPgVector(uPrime),
          updated_at: new Date().toISOString()
        },
        { onConflict: "user_id" }
      )
      .select()
      .single();
    if (upErr) return res.status(500).json({ error: "Failed to save updated preference", details: upErr.message });
    


    

    const voteData = {
      user_id: userId,
      song: song_title,
      vote_value: parseInt(vote_value, 10), // Convert to integer
      vote_time: new Date().toISOString(),
    };

    const { data, error } = await req.supabase
      .from('vote')
      .insert(voteData)
      .select()
      .single();

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    res.status(201).json({
      success: true,
      message: 'Vote recorded successfully',
      data,
    });
  } catch (err) {
    console.error('Create vote error:', err);
    res.status(500).json({ error: 'Failed to record vote' });
  }
});

/**
 * PUT /api/votes/:id
 * Update an existing vote
 * Body: { song: string, vote_value: number }
 */
router.put('/votes/:id', authenticateToken, async (req, res) => {
  try {
    const voteId = req.params.id;
    const { song, vote_value } = req.body;

    const updateData = {};
    
    // Only update fields that are provided
    if (song !== undefined) {
      updateData.song = song;
    }
    if (vote_value !== undefined) {
      updateData.vote_value = parseInt(vote_value, 10); // Convert to integer
    }
    
    updateData.vote_time = new Date().toISOString();

    const { data, error } = await req.supabase
      .from('vote')
      .update(updateData)
      .eq('id', voteId)
      .eq('user_id', req.user.id) // Ensure user can only update their own votes
      .select()
      .single();

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    res.status(200).json({
      success: true,
      message: 'Vote updated successfully',
      data,
    });
  } catch (err) {
    console.error('Update vote error:', err);
    res.status(500).json({ error: 'Failed to update vote' });
  }
});

/**
 * DELETE /api/votes/:id
 * Delete a vote
 */
router.delete('/votes/:id', authenticateToken, async (req, res) => {
  try {
    const voteId = req.params.id;

    const { error } = await req.supabase
      .from('vote')
      .delete()
      .eq('id', voteId)
      .eq('user_id', req.user.id); // Ensure user can only delete their own votes

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    res.status(200).json({
      success: true,
      message: 'Vote deleted successfully',
    });
  } catch (err) {
    console.error('Delete vote error:', err);
    res.status(500).json({ error: 'Failed to delete vote' });
  }
});

router.get('/current-song', async (_req, res) => {
  try {
    if (!serviceClient) {
      return res.json({
        success: true,
        data: process.env.CURRENT_SONG_NAME
          ? {
              reference_id: null,
              song: process.env.CURRENT_SONG_NAME,
              updated_at: null,
            }
          : null,
        message: 'Current song source not configured',
      });
    }

    const { data, error } = await serviceClient
      .from('vote')
      .select('id, song, vote_time')
      .order('vote_time', { ascending: false })
      .limit(1);

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    const latest = Array.isArray(data) ? data[0] : null;

    res.json({
      success: true,
      data: latest
        ? {
            reference_id: latest.id,
            song: latest.song,
            updated_at: latest.vote_time,
          }
        : null,
    });
  } catch (err) {
    console.error('Get current song error:', err);
    res.status(500).json({ error: 'Failed to load current song' });
  }
});

module.exports = router;
