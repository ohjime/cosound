import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { clearAuthData } from '../lib/auth';
import styles from './Login.module.css';

export const Login = () => {
  const { signInWithSpotify } = useAuth();
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isClearing, setIsClearing] = useState(false);

  const handleSpotifyLogin = async () => {
    setIsLoading(true);
    setError(null);
    try {
      await signInWithSpotify();
      // OAuth redirect happens automatically
    } catch (error) {
      setError(error.message);
      setIsLoading(false);
    }
  };

  const handleClearCache = async () => {
    setIsClearing(true);
    try {
      await clearAuthData();
      alert('✅ Cache cleared! All session data removed.');
    } catch (err) {
      console.error('Failed to clear cache:', err);
      alert('❌ Failed to clear cache. Check console for details.');
    } finally {
      setIsClearing(false);
    }
  };

  return (
    <div className={styles['login-page']}>
      {/* Animated Background Particles */}
      <div className={styles['particle-field']}>
        {[...Array(20)].map((_, i) => (
          <div key={i} className={styles['particle']} style={{
            '--delay': `${i * 0.1}s`,
            '--duration': `${3.5 + (i % 3)}s`,
            '--x': `${Math.random() * 100}%`,
            '--y': `${Math.random() * 100}%`,
          }}></div>
        ))}
      </div>

      {/* Morphing Background Blobs */}
      <div className={styles['login-background-blobs']}>
        <div className={`${styles['login-blob']} ${styles['login-blob-1']}`}></div>
        <div className={`${styles['login-blob']} ${styles['login-blob-2']}`}></div>
        <div className={`${styles['login-blob']} ${styles['login-blob-3']}`}></div>
        <div className={`${styles['login-blob']} ${styles['login-blob-4']}`}></div>
      </div>

      {/* Sound Wave Ripples */}
      <div className={styles['sound-waves']}>
        <div className={styles['wave']}></div>
        <div className={styles['wave']}></div>
        <div className={styles['wave']}></div>
        <div className={styles['wave']}></div>
        <div className={styles['wave']}></div>
      </div>

      <div className={styles['login-container']}>
        {/* Main Card */}
        <div className={styles['login-card']}>
          {/* Rotating Glow Effect */}
          <div className={styles['card-glow']}></div>

          {/* Logo/Brand Section */}
          <div className={styles['login-header']}>
            <div className={styles['logo-wrapper']}>
              <div className={styles['logo-pulse-ring']}></div>
              <div className={styles['logo-pulse-ring']}></div>
              <div className={styles['login-logo']}>
                <svg fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
                </svg>
              </div>
            </div>
            <h1 className={styles['login-title']}>
              <span className={styles['title-word']}>Cosounds</span>
            </h1>
            <p className={styles['login-subtitle']}>
              <span className={styles['subtitle-word']}>Find</span>
              <span className={styles['subtitle-word']}>your</span>
              <span className={styles['subtitle-word']}>focus</span>
              <span className={styles['subtitle-word']}>sound</span>
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
            onClick={handleSpotifyLogin}
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
                <div className={styles['button-icon-wrapper']}>
                  <svg className={styles['login-button-icon']} viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.84-.179-.84-.66 0-.419.24-.66.54-.779 4.56-1.021 8.52-.6 11.64 1.32.42.18.479.659.242 1.02zm1.44-3.3c-.301.42-.841.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.78.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.601.18-1.2.78-1.381 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.42 1.56-.299.421-1.02.599-1.559.3z"/>
                  </svg>
                </div>
                <span className={styles['button-text']}>Continue with Spotify</span>
                <div className={styles['button-shine']}></div>
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
