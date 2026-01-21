const { Router } = require('express');
const { createClient } = require('@supabase/supabase-js');
const { authenticateToken } = require('../middleware/auth.js');

const router = Router();

/**
 * GET /api/leaderboard
 * Get top 10 voters for the current month (public endpoint)
 */
router.get('/', async (req, res) => {
  try {
    // Create admin client for public data access
    const supabase = createClient(
      process.env.SUPABASE_URL,
      process.env.SUPABASE_ANON_KEY
    );
    
    // Get start of current month
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
    
    // Get all votes this month with user profiles
    const { data: votes, error } = await supabase
      .from('vote')
      .select(`
        user_id,
        vote_value,
        profiles!inner(display_name, name)
      `)
      .gte('vote_time', monthStart);
    
    if (error) {
      console.error('Leaderboard query error:', error);
      return res.status(400).json({ error: error.message });
    }
    
    // Aggregate votes by user
    const userVotes = {};
    
    votes.forEach(vote => {
      const userId = vote.user_id;
      
      if (!userVotes[userId]) {
        // Use display_name if set, otherwise fallback to first name from Google
        const displayName = vote.profiles.display_name || 
                           vote.profiles.name?.split(' ')[0] || 
                           'Anonymous';
        
        userVotes[userId] = {
          user_id: userId,
          display_name: displayName,
          total_votes: 0,
          positive_votes: 0,
          negative_votes: 0
        };
      }
      
      userVotes[userId].total_votes++;
      
      if (vote.vote_value > 0) {
        userVotes[userId].positive_votes++;
      } else if (vote.vote_value < 0) {
        userVotes[userId].negative_votes++;
      }
    });
    
    // Convert to array and sort by total votes
    const leaderboard = Object.values(userVotes)
      .sort((a, b) => b.total_votes - a.total_votes)
      .slice(0, 10); // Top 10
    
    res.json({
      success: true,
      month: now.toLocaleString('default', { month: 'long', year: 'numeric' }),
      count: leaderboard.length,
      data: leaderboard
    });
  } catch (err) {
    console.error('Leaderboard error:', err);
    res.status(500).json({ error: 'Failed to fetch leaderboard' });
  }
});

/**
 * GET /api/leaderboard/me
 * Get current user's voting stats for the month (protected endpoint)
 */
router.get('/me', authenticateToken, async (req, res) => {
  try {
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).toISOString();
    
    // Get user's vote count this month
    const { data: myVotes, error } = await req.supabase
      .from('vote')
      .select('vote_value')
      .eq('user_id', req.user.id)
      .gte('vote_time', monthStart);
    
    if (error) {
      console.error('My stats query error:', error);
      return res.status(400).json({ error: error.message });
    }
    
    // Get profile for display name
    const { data: profile } = await req.supabase
      .from('profiles')
      .select('display_name, name')
      .eq('id', req.user.id)
      .single();
    
    const displayName = profile?.display_name || 
                       profile?.name?.split(' ')[0] || 
                       'You';
    
    const stats = {
      user_id: req.user.id,
      display_name: displayName,
      total_votes: myVotes.length,
      positive_votes: myVotes.filter(v => v.vote_value > 0).length,
      negative_votes: myVotes.filter(v => v.vote_value < 0).length
    };
    
    res.json({
      success: true,
      month: now.toLocaleString('default', { month: 'long', year: 'numeric' }),
      data: stats
    });
  } catch (err) {
    console.error('My stats error:', err);
    res.status(500).json({ error: 'Failed to fetch stats' });
  }
});

module.exports = router;
