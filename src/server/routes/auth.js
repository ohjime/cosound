import { Router } from 'express';
import { authenticateToken, requireRole } from '../middleware/auth.js';

router.get('/profile', authenticateToken, async (req, res) => {
  try {
    // Use the per-request client (acts as the user)
    // RLS ensures they only see their own profile
    const { data, error } = await req.supabase!
      .from('user_profiles')
      .select('*')
      .eq('id', req.user!.id)
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
