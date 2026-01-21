import { useEffect, useRef, useState } from 'react';
import { useParams, useLocation, useNavigate } from 'react-router-dom';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { supabase } from '../lib/supabase';
import { apiClient } from '../lib/apt';
import styles from './VoteConfirmation.module.css';

const formatSongTitle = (title = '') =>
  title
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const VoteConfirmation = () => {
  const { voteValue } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [song, setSong] = useState('');
  const [canonicalSong, setCanonicalSong] = useState('');
  const [isMobile, setIsMobile] = useState(false);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const voteSubmitRef = useRef(false);

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

    const displayStored = location.state?.song || sessionStorage.getItem('voteSong');
    if (displayStored) {
      setSong(displayStored);
    }
    const canonicalStored = location.state?.canonicalSong || sessionStorage.getItem('voteCanonicalSong');
    if (canonicalStored) {
      setCanonicalSong(canonicalStored);
    }

    // Check if vote already submitted
    if (voteSubmitRef.current) {
      return;
    }

    const submitVoteOnLoad = async () => {
      voteSubmitRef.current = true;

      try {
        // Ensure active session exists
        const sessionCheck = await apiClient('/api/session');
        if (!sessionCheck.active) {
          console.log('No active session, creating one...');
          await apiClient('/api/checkin', { method: 'POST' });
        }

        // Get current song from state/storage or API
        let songToVote =
          location.state?.canonicalSong ||
          sessionStorage.getItem('voteCanonicalSong') ||
          location.state?.song ||
          sessionStorage.getItem('voteSong');

        if (!songToVote) {
          try {
            const songResponse = await apiClient('/api/model/currentSong');
            songToVote = songResponse?.current_song || 'Unknown track';
          } catch (err) {
            console.warn('Could not fetch current song, using fallback');
            songToVote = 'Unknown track';
          }
        }

        const formatted = formatSongTitle(songToVote) || 'Unknown track';
        setSong(formatted);
        setCanonicalSong(songToVote);
        sessionStorage.setItem('voteCanonicalSong', songToVote);

        // Submit vote
        const numericVote = voteValue === '0' ? -1 : 1;
        await apiClient('/api/votes', {
          method: 'POST',
          body: JSON.stringify({
            song: songToVote,
            vote_value: numericVote,
            nfctagid: 'direct-url',
          }),
        });

        console.log(`✅ Vote submitted: ${numericVote} for "${songToVote}"`);
      } catch (error) {
        console.error('❌ Vote submission failed:', error);
      }
    };

    submitVoteOnLoad();
  }, [voteValue, navigate, location.state]);

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
            <p className={styles['song-name']}>
              {song || 'Loading...'}
            </p>
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
                  sessionStorage.removeItem('voteCanonicalSong');
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

