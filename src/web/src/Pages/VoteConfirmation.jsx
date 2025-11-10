import { useEffect, useState } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { supabase } from '../lib/supabase';
import styles from './VoteConfirmation.module.css';

const VoteConfirmation = () => {
  const { voteValue } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [song, setSong] = useState('Frog Noises');
  const [isMobile, setIsMobile] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    // Check if user is logged in
    const checkAuth = async () => {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        setIsLoggedIn(!!session);
      } catch (error) {
        console.error('Error checking auth:', error);
        setIsLoggedIn(false);
      } finally {
        setCheckingAuth(false);
      }
    };

    checkAuth();

    // Listen for auth changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setIsLoggedIn(!!session);
    });

    return () => subscription.unsubscribe();
  }, []);

  useEffect(() => {
    // Validate voteValue - only allow 0 or 1
    if (voteValue !== '0' && voteValue !== '1') {
      navigate('/vote', { replace: true });
      return;
    }

    // Check if user came from voting (prevent direct URL access)
    const voteSubmitted = sessionStorage.getItem('voteSubmitted');
    const storedVoteValue = sessionStorage.getItem('voteValue');
    
    // If no vote was submitted or voteValue doesn't match, redirect to vote page
    if (!voteSubmitted || storedVoteValue !== voteValue) {
      navigate('/vote', { replace: true });
      return;
    }

    // Get song from location state or sessionStorage (dummy data)
    if (location.state?.song) {
      setSong(location.state.song);
    } else if (sessionStorage.getItem('voteSong')) {
      setSong(sessionStorage.getItem('voteSong'));
    } else {
      // Fallback to dummy song if nothing is available
      setSong('Frog Noises');
    }
  }, [location.state, voteValue, navigate]);

  const isPositive = voteValue === '1';

  return (
    <div className={styles['confirmation-page']}>
      {/* Animated Background Particles */}
      <div className={styles['particle-field']}>
        {[...Array(12)].map((_, i) => (
          <div key={i} className={styles['particle']} style={{
            '--delay': `${i * 0.1}s`,
            '--duration': `${3 + (i % 3)}s`,
            '--x': `${Math.random() * 100}%`,
            '--y': `${Math.random() * 100}%`,
          }}></div>
        ))}
      </div>

      {/* Morphing Background Blobs */}
      <div className={styles['background-blobs']}>
        <div className={`${styles.blob} ${styles['blob-1']}`}></div>
        <div className={`${styles.blob} ${styles['blob-2']}`}></div>
      </div>

      {/* Sound Wave Ripples */}
      <div className={styles['sound-waves']}>
        <div className={styles['wave']}></div>
        <div className={styles['wave']}></div>
        <div className={styles['wave']}></div>
      </div>

      <div className={styles['confirmation-container']}>
        <div className={styles['confirmation-card']}>
          {/* Icon with Particle Burst */}
          <div className={styles['icon-wrapper']}>
            <div className={styles['particle-burst']}>
              {[...Array(12)].map((_, i) => (
                <div 
                  key={i} 
                  className={styles['burst-particle']}
                  style={{
                    '--delay': `${i * 0.05}s`,
                  }}
                ></div>
              ))}
            </div>
            <div className={`${styles['icon-container']} ${isPositive ? styles.positive : styles.negative}`}>
              {isPositive ? (
                <ThumbsUp size={80} />
              ) : (
                <ThumbsDown size={80} />
              )}
            </div>
            {/* Pulsing Rings */}
            <div className={styles['pulse-ring']}></div>
            <div className={styles['pulse-ring']}></div>
          </div>

          {/* Message with Staggered Reveal */}
          <h1 className={styles['confirmation-title']}>
            <span className={styles['title-word']}>
              {isPositive ? "You" : "You"}
            </span>
            <span className={styles['title-word']}>
              {isPositive ? "voted" : "voted"}
            </span>
            <span className={styles['title-word']}>
              {isPositive ? "positively" : "negatively"}
            </span>
            <span className={styles['title-word']}>
              for
            </span>
            <span className={styles['title-word']}>
              this
            </span>
            <span className={styles['title-word']}>
              sound
            </span>
          </h1>

          {/* Song Display with Morphing Border */}
          <div className={styles['song-display']}>
            <div className={styles['song-border-animation']}></div>
            <p className={styles['song-label']}>Song:</p>
            <p className={styles['song-name']}>{song}</p>
          </div>

          {/* Back Button / Login Button */}
          {!checkingAuth && (
            <button 
              onClick={() => {
                if (isLoggedIn) {
                  // Clear the vote flag when going back
                  sessionStorage.removeItem('voteSubmitted');
                  sessionStorage.removeItem('voteValue');
                  sessionStorage.removeItem('voteSong');
                  navigate('/vote');
                } else {
                  // Navigate to login page
                  navigate('/login');
                }
              }}
              className={styles['back-button']}
            >
              <span className={styles['button-text']}>
                {isLoggedIn ? 'Back to Voting' : 'Sign up or login to see progress'}
              </span>
              <div className={styles['button-shine']}></div>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default VoteConfirmation;

