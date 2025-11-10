import { supabase } from './supabase';

/**
 * Clear all authentication data from browser storage
 */
export async function clearAuthData() {
  try {
    // Sign out from Supabase (clears session)
    await supabase.auth.signOut();

    // Clear all localStorage items related to auth
    const keysToRemove = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && (
        key.includes('supabase') ||
        key.includes('auth') ||
        key.includes('sb-') ||
        key.includes('hasCompleted')
      )) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach(key => localStorage.removeItem(key));

    // Clear sessionStorage
    sessionStorage.clear();

    console.log('✅ Auth data cleared');
  } catch (err) {
    console.error('Failed to clear auth data:', err);
  }
}

/**
 * Validate current session and clear if invalid
 * Returns true if session is valid, false otherwise
 */
export async function validateSession() {
  try {
    const { data: { session }, error: sessionError } = await supabase.auth.getSession();

    if (sessionError || !session) {
      console.log('No valid session found');
      await clearAuthData();
      return false;
    }

    // Try to fetch user data to verify token is valid
    const { data: { user }, error: userError } = await supabase.auth.getUser();

    if (userError || !user) {
      console.log('Session token invalid or user deleted:', userError?.message);
      await clearAuthData();
      return false;
    }

    console.log('✅ Session valid for user:', user.email);
    return true;
  } catch (err) {
    console.error('Session validation error:', err);
    await clearAuthData();
    return false;
  }
}

/**
 * Check if user token is expired
 */
export function isTokenExpired(session) {
  if (!session?.expires_at) return true;

  const expiresAt = session.expires_at * 1000; // Convert to milliseconds
  const now = Date.now();
  const fiveMinutes = 5 * 60 * 1000;

  // Token expired or expires in less than 5 minutes
  return expiresAt - now < fiveMinutes;
}

/**
 * Automatically refresh token if needed
 */
export async function ensureValidSession() {
  try {
    const { data: { session } } = await supabase.auth.getSession();

    if (!session) {
      return null;
    }

    // If token is expired or about to expire, refresh it
    if (isTokenExpired(session)) {
      console.log('Token expiring soon, refreshing...');
      const { data: { session: newSession }, error } = await supabase.auth.refreshSession();

      if (error || !newSession) {
        console.error('Failed to refresh session:', error?.message);
        await clearAuthData();
        return null;
      }

      console.log('✅ Token refreshed');
      return newSession;
    }

    return session;
  } catch (err) {
    console.error('Session refresh error:', err);
    await clearAuthData();
    return null;
  }
}
