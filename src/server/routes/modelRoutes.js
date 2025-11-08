const express = require('express');
const router = express.Router();
const { createClient } = require('@supabase/supabase-js');
const authenticateApiKey = require('../middleware/authenticateApiKey');

// Initialize Supabase client
const supabase = createClient(
  process.env.SUPABASE_URL,
  process.env.SUPABASE_ANON_KEY
);

// All routes protected by API key authentication
router.use(authenticateApiKey);

// ============================================
// MODEL DATA ENDPOINTS
// ============================================

/**
 * GET /api/model/users
 * Get all users
 */
router.get('/users', async (req, res) => {
  try {
    const { data, error } = await supabase
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

module.exports = router;
