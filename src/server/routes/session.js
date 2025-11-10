const express = require('express');
const router = express.Router();
const { authenticateToken } = require('../middleware/auth');

// ============================================
// SESSION ENDPOINTS
// ============================================

/**
 * POST /api/checkin
 * Create a 1-hour session (auto check-in)
 */
router.post('/checkin', authenticateToken, async (req, res) => {
  try {
    const now = new Date();
    const expiresAt = new Date(now.getTime() + 60 * 60 * 1000); 
    
    // Mark any existing active sessions as inactive
    await req.supabase
      .from('sessions')
      .update({ status: 'inactive' })
      .eq('user_id', req.user.id)
      .eq('status', 'active');
    
    // Create new session
    const { data, error } = await req.supabase
      .from('sessions')
      .insert({
        user_id: req.user.id,
        checked_in_at: now.toISOString(),
        expires_at: expiresAt.toISOString(),
        status: 'active'
      })
      .select()
      .single();
    
    if (error) {
      return res.status(400).json({ error: error.message });
    }
    
    res.json({
      success: true,
      message: '1-hour vibe pass activated',
      data: {
        session_id: data.id,
        expires_at: data.expires_at,
        expires_in_minutes: 60
      }
    });
  } catch (err) {
    console.error('Check-in error:', err);
    res.status(500).json({ error: 'Failed to check in' });
  }
});

/**
 * POST /api/checkout
 * Manual checkout (optional - expires automatically after 1 hour)
 */
router.post('/checkout', authenticateToken, async (req, res) => {
  try {
    const { error } = await req.supabase
      .from('sessions')
      .update({ status: 'inactive' })
      .eq('user_id', req.user.id)
      .eq('status', 'active');
    
    if (error) {
      return res.status(400).json({ error: error.message });
    }
    
    res.json({
      success: true,
      message: 'Checked out successfully'
    });
  } catch (err) {
    console.error('Checkout error:', err);
    res.status(500).json({ error: 'Failed to check out' });
  }
});

/**
 * GET /api/session
 * Get current user's active session status
 */
router.get('/session', authenticateToken, async (req, res) => {
  try {
    const now = new Date().toISOString();
    
    const { data, error } = await req.supabase
      .from('sessions')
      .select('*')
      .eq('user_id', req.user.id)
      .eq('status', 'active')
      .gt('expires_at', now)
      .order('checked_in_at', { ascending: false })
      .limit(1)
      .single();
    
    if (error && error.code !== 'PGRST116') {
      return res.status(400).json({ error: error.message });
    }
    
    if (!data) {
      return res.json({
        success: true,
        active: false,
        message: 'No active session'
      });
    }
    
    // Calculate remaining time
    const expiresAt = new Date(data.expires_at);
    const nowDate = new Date();
    const minutesRemaining = Math.floor((expiresAt - nowDate) / (1000 * 60));
    
    res.json({
      success: true,
      active: true,
      data: {
        session_id: data.id,
        checked_in_at: data.checked_in_at,
        expires_at: data.expires_at,
        minutes_remaining: minutesRemaining
      }
    });
  } catch (err) {
    console.error('Get session error:', err);
    res.status(500).json({ error: 'Failed to get session' });
  }
});

module.exports = router;
