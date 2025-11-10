const { Router } = require('express');
const { authenticateToken } = require('../middleware/auth.js');

const router = Router();

router.get('/profile', authenticateToken, async (req, res) => {
  try {
    // Use the per-request client (acts as the user)
    // RLS ensures they only see their own profile
    const { data, error } = await req.supabase
      .from('profiles')
      .select('id, email, name, display_name')
      .eq('id', req.user.id)
      .single();

    if (error) {
      return res.status(400).json({ error: error.message });
    }

    res.json(data);
  } catch (err) {
    console.error('Profile fetch error:', err);
    res.status(500).json({ error: 'Failed to fetch profile' });
  }
});

/**
 * POST /api/auth/display-name
 * Set or update user's display name
 * Body: { display_name: string }
 */
router.post('/display-name', authenticateToken, async (req, res) => {
  try {
    const { display_name } = req.body;
    
    // Validate display name
    if (!display_name || display_name.trim().length === 0) {
      return res.status(400).json({ error: 'Display name required' });
    }
    
    // Basic validation
    if (display_name.length > 50) {
      return res.status(400).json({ 
        error: 'Display name too long (max 50 characters)' 
      });
    }
    
    const { data, error } = await req.supabase
      .from('profiles')
      .update({ display_name: display_name.trim() })
      .eq('id', req.user.id)
      .select()
      .single();
    
    if (error) {
      return res.status(400).json({ error: error.message });
    }
    
    res.json({
      success: true,
      message: 'Display name updated',
      data
    });
  } catch (err) {
    console.error('Set display name error:', err);
    res.status(500).json({ error: 'Failed to set display name' });
  }
});




module.exports = router;
