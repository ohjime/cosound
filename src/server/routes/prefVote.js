const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');

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
      // PGRST116 = row not found
      return res.status(400).json({ error: error.message });
    }

    // Parse the preference string back to JSON object
    let responseData = null;
    if (data) {
      responseData = {
        ...data,
        preference: JSON.parse(data.preference),
      };
    }

    res.status(200).json({
      success: true,
      data: responseData,
    });
  } catch (err) {
    console.error('Get preferences error:', err);
    res.status(500).json({ error: 'Failed to fetch preferences' });
  }
});

/**
 * POST /api/preferences
 * Create or update user's preferences
 * Body: JSON object with preference data
 */
router.post('/preferences', authenticateToken, async (req, res) => {
  try {
    const preferenceData = {
      user_id: req.user.id,
      preference: JSON.stringify(req.body), // Convert JSON to string for text field
      updated_at: new Date().toISOString(),
    };

    const { data, error } = await req.supabase
      .from('preferences')
      .upsert(preferenceData, {
        onConflict: 'user_id',
      })
      .select()
      .single();

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    // Parse the preference back to JSON for response
    const responseData = {
      ...data,
      preference: JSON.parse(data.preference),
    };

    res.status(200).json({
      success: true,
      message: 'Preferences saved successfully',
      data: responseData,
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

/**
 * POST /api/votes
 * Create a new vote
 * Body: { song: string, vote_value: number }
 */
router.post('/votes', authenticateToken, async (req, res) => {
  try {
    const { song, vote_value } = req.body;

    // Validate required fields
    if (!song || vote_value === undefined) {
      return res.status(400).json({ 
        error: 'Song and vote_value are required' 
      });
    }

    const voteData = {
      user_id: req.user.id,
      song: song,
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

module.exports = router;
