import { useAtom } from 'jotai';
import { useEffect } from 'react';
import { userAtom, sessionAtom, authLoadingAtom } from '../lib/atoms';
import { supabase } from '../lib/supabase';
import { validateSession, clearAuthData } from '../lib/auth';

/**
 * Centralized auth hook using Jotai for state management
 */
export function useAuth() {
  const [user, setUser] = useAtom(userAtom);
  const [session, setSession] = useAtom(sessionAtom);
  const [loading, setLoading] = useAtom(authLoadingAtom);

  useEffect(() => {
    // Get initial session and validate it
    const initAuth = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession();

        // Validate session if it exists
        if (session) {
          const isValid = await validateSession();
          if (isValid) {
            setSession(session);
            setUser(session?.user ?? null);
          } else {
            // Invalid session - clear it
            await clearAuthData();
            setSession(null);
            setUser(null);
          }
        } else {
          setSession(null);
          setUser(null);
        }
      } catch (err) {
        console.error('Error initializing auth:', err);
        setSession(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    initAuth();

    // Listen for auth changes
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange(async (event, session) => {
      console.log('Auth state changed:', event);

      if (event === 'SIGNED_OUT' || event === 'USER_DELETED') {
        await clearAuthData();
        setSession(null);
        setUser(null);
      } else if (event === 'SIGNED_IN' || event === 'TOKEN_REFRESHED') {
        setSession(session);
        setUser(session?.user ?? null);
      } else if (event === 'USER_UPDATED') {
        setSession(session);
        setUser(session?.user ?? null);
      }

      setLoading(false);
    });

    // Cleanup subscription
    return () => subscription.unsubscribe();
  }, [setUser, setSession, setLoading]);

  /**
   * Sign in with Spotify OAuth
   */
  const signInWithSpotify = async () => {
    const redirectUrl = `${window.location.origin}/auth/callback`;

    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'spotify',
      options: {
        redirectTo: redirectUrl,
        scopes: 'user-top-read user-read-email', // Request top artists/genres and email
      },
    });

    if (error) throw error;
    return data;
  };

  /**
   * Sign out - clears session in Supabase and triggers the listener
   */
  const signOut = async () => {
    try {
      await clearAuthData(); // Clear all local storage
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
    } catch (err) {
      console.error('Error signing out:', err);
      throw err;
    }
  };

  return {
    user,
    session,
    loading,
    signInWithSpotify,
    signOut,
    isAuthenticated: Boolean(user && session),
  };
}
