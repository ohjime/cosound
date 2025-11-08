import { useState } from 'react';
import { supabase } from '../lib/supabase';
import styles from './Login.module.css';

export const Login = () => {
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleGoogleLogin = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      });
      if (error) throw error;
    } catch (error) {
      setError(error.message);
      setIsLoading(false);
    }
  };

  return (
    <div className={styles['login-page']}>
      {/* Animated background blobs */}
      <div className={styles['login-background-blobs']}>
        <div className={`${styles['login-blob']} ${styles['login-blob-1']}`}></div>
        <div className={`${styles['login-blob']} ${styles['login-blob-2']}`}></div>
        <div className={`${styles['login-blob']} ${styles['login-blob-3']}`}></div>
      </div>

      <div className={styles['login-container']}>
        {/* Main Card */}
        <div className={styles['login-card']}>
          {/* Logo/Brand Section */}
          <div className={`${styles['login-header']} ${styles['fade-in-down']}`}>
            <div className={styles['login-logo']}>
              <svg fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
              </svg>
            </div>
            <h1 className={styles['login-title']}>
              Sound Guys
            </h1>
            <p className={styles['login-subtitle']}>
              Find your focus sound
            </p>
            <div className={styles['login-title-lines']}>
              <div className={`${styles['login-title-line']} ${styles['login-title-line-1']}`}></div>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className={`${styles['error-message']} ${styles.shake}`}>
              <svg className={styles['error-icon']} fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <p className={styles['error-text']}>{error}</p>
            </div>
          )}

          {/* Login Button */}
          <button
            onClick={handleGoogleLogin}
            disabled={isLoading}
            className={styles['login-button']}
          >
            {isLoading ? (
              <>
                <div className={styles['login-spinner']}></div>
                <span>Connecting...</span>
              </>
            ) : (
              <>
                <svg className={styles['login-button-icon']} viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  />
                </svg>
                <span>Continue with Google</span>
              </>
            )}
          </button>

          {/* Footer Text */}
          <p className={styles['login-footer']}>
            By signing in, you agree to our terms of service
          </p>
        </div>

        {/* Decorative Elements */}
        {/* <div className={styles['login-decorative-dots']}>
          <div className={styles['login-dots']}>
            <div className={`${styles['login-dot']} ${styles['login-dot-1']}`}></div>
            <div className={`${styles['login-dot']} ${styles['login-dot-2']}`}></div>
            <div className={`${styles['login-dot']} ${styles['login-dot-3']}`}></div>
          </div>
        </div> */}
      </div>
    </div>
  );
};
