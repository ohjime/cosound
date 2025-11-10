import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { validateSession } from '../lib/auth';
import { supabase } from '../lib/supabase';

/**
 * Hook to validate session on mount and listen for auth changes
 * Automatically clears invalid sessions and redirects to login
 */
export function useSessionValidator() {
  const navigate = useNavigate();
  const [isValidating, setIsValidating] = useState(true);
  const [isValid, setIsValid] = useState(false);

  useEffect(() => {
    // Validate session on mount
    const checkSession = async () => {
      const valid = await validateSession();
      setIsValid(valid);
      setIsValidating(false);

      // If invalid and not on login page, redirect
      if (!valid && window.location.pathname !== '/login') {
        console.log('Invalid session detected, redirecting to login');
        navigate('/login', { replace: true });
      }
    };

    checkSession();

    // Listen for auth state changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      async (event, session) => {
        console.log('Auth state changed:', event);

        if (event === 'SIGNED_OUT' || event === 'USER_DELETED') {
          console.log('User signed out or deleted, redirecting to login');
          setIsValid(false);
          navigate('/login', { replace: true });
        }

        if (event === 'SIGNED_IN') {
          console.log('User signed in');
          setIsValid(true);
        }

        if (event === 'TOKEN_REFRESHED') {
          console.log('Token refreshed successfully');
        }

        if (event === 'USER_UPDATED') {
          console.log('User updated');
        }
      }
    );

    // Cleanup subscription
    return () => {
      subscription.unsubscribe();
    };
  }, [navigate]);

  return { isValidating, isValid };
}
