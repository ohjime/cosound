import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ThumbsUp, ThumbsDown, User, LogOut } from 'lucide-react';
import { supabase } from '../lib/supabase';
import styles from './Vote.module.css';
import easterEggImage from '../assets/67.jpeg';
import easterEggAudio from '../assets/67.wav';

const KONAMI_SEQUENCE = [
  'ArrowUp',
  'ArrowUp',
  'ArrowDown',
  'ArrowDown',
  'ArrowLeft',
  'ArrowRight',
  'ArrowLeft',
  'ArrowRight',
  'b',
  'a',
  'Enter',
];

const normalizeKey = (key) => (key.length === 1 ? key.toLowerCase() : key);

const Vote = () => {
  // Dummy data for testing
  const DUMMY_SONGS = [
    { id: '1', song: 'Frog Noises' },
    { id: '2', song: 'Ocean Waves' },
    { id: '3', song: 'Rain Sounds' },
    { id: '4', song: 'Forest Ambience' },
  ];

  // NFC Tag mapping: tagId -> voteValue
  const NFC_TAG_MAPPING = {
    '1234567': 1, // Thumbs up
    '1234568': 0, // Thumbs down
  };

  // Initialize with default song immediately (no loading delay for dummy data)
  const [currentSong, setCurrentSong] = useState(() => {
    const randomSong = DUMMY_SONGS[Math.floor(Math.random() * DUMMY_SONGS.length)];
    return randomSong.song;
  });
  const [selectedVote, setSelectedVote] = useState(null);
  const [hasVoted, setHasVoted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [songId, setSongId] = useState(() => {
    const randomSong = DUMMY_SONGS[Math.floor(Math.random() * DUMMY_SONGS.length)];
    return randomSong.id;
  });
  const [songName, setSongName] = useState(() => {
    const randomSong = DUMMY_SONGS[Math.floor(Math.random() * DUMMY_SONGS.length)];
    return randomSong.song;
  });
  const [isLoadingSong, setIsLoadingSong] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [nfcTagDetected, setNfcTagDetected] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [isEasterEggActive, setIsEasterEggActive] = useState(false);
  const konamiIndexRef = useRef(0);
  const eggAudioRef = useRef(null);
  const authSubscriptionRef = useRef(null);
  const normalizedSequence = useMemo(
    () => KONAMI_SEQUENCE.map((key) => normalizeKey(key)),
    []
  );

  useEffect(() => {
    // Check if mobile
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  useEffect(() => {
    let isMounted = true;

    const initialiseAuth = async () => {
      try {
        const { data } = await supabase.auth.getSession();
        if (isMounted) {
          setIsLoggedIn(Boolean(data?.session));
        }
      } catch (error) {
        console.warn('Unable to determine auth session', error);
      }
    };

    initialiseAuth();

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      setIsLoggedIn(Boolean(session));
    });

    authSubscriptionRef.current = subscription;

    return () => {
      isMounted = false;
      const sub = authSubscriptionRef.current?.subscription ?? authSubscriptionRef.current;
      if (sub && typeof sub.unsubscribe === 'function') {
        sub.unsubscribe();
      }
    };
  }, []);

  useEffect(() => {
    const audio = new Audio(easterEggAudio);
    audio.preload = 'auto';
    const handleEnded = () => {
      setIsEasterEggActive(false);
    };

    audio.addEventListener('ended', handleEnded);
    eggAudioRef.current = audio;

    return () => {
      audio.removeEventListener('ended', handleEnded);
      audio.pause();
      eggAudioRef.current = null;
    };
  }, []);

  const triggerEasterEgg = useCallback(() => {
    if (!isLoggedIn) {
      return;
    }

    const audio = eggAudioRef.current;
    if (!audio) {
      return;
    }

    try {
      audio.pause();
      audio.currentTime = 0;
    } catch (error) {
      console.warn('Unable to reset easter egg audio', error);
    }

    setIsEasterEggActive(true);
    audio
      .play()
      .catch((error) => {
        console.warn('Easter egg audio failed to play', error);
        setIsEasterEggActive(false);
      });
  }, [isLoggedIn]);

  useEffect(() => {
    if (!isLoggedIn) {
      konamiIndexRef.current = 0;
      return undefined;
    }

    const handleKeyDown = (event) => {
      const key = normalizeKey(event.key);
      const expected = normalizedSequence[konamiIndexRef.current];

      if (key === expected) {
        konamiIndexRef.current += 1;
        if (konamiIndexRef.current === normalizedSequence.length) {
          konamiIndexRef.current = 0;
          triggerEasterEgg();
        }
      } else {
        const firstKey = normalizedSequence[0];
        konamiIndexRef.current = key === firstKey ? 1 : 0;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isLoggedIn, normalizedSequence, triggerEasterEgg]);

  useEffect(() => {
    if (!isLoggedIn && isEasterEggActive) {
      setIsEasterEggActive(false);
      if (eggAudioRef.current) {
        try {
          eggAudioRef.current.pause();
          eggAudioRef.current.currentTime = 0;
        } catch (error) {
          console.warn('Unable to stop easter egg audio', error);
        }
      }
    }
  }, [isLoggedIn, isEasterEggActive]);


  // Simulate API call to POST /api/votes
  const simulateApiCall = async (voteData, nfctagid) => {
    const apiEndpoint = 'http://localhost:3000/api/votes';
    const requestBody = {
      song: voteData.song,
      vote_value: voteData.vote_value,
      nfctagid: nfctagid || null, // Include NFC tag ID if present
    };

    // Log API call to console
    console.log('=== API CALL SIMULATION ===');
    console.log('Endpoint:', apiEndpoint);
    console.log('Method: POST');
    console.log('Headers:', {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer dummy-token',
    });
    console.log('Request Body:', JSON.stringify(requestBody, null, 2));
    console.log('==========================');

    // Simulate API response
    return {
      success: true,
      message: 'Vote recorded successfully',
      data: voteData,
    };
  };

  const handleVoteFromNFC = async (voteValue, nfctagid) => {
    // Prevent duplicate votes
    if (hasVoted || isSubmitting) {
      return;
    }
    
    // Ensure we have a song name (should always be set from initial state)
    const activeSong = songName || currentSong;
    if (!activeSong) {
      console.warn('No song available for voting');
      return;
    }

    setSelectedVote(voteValue);
    setIsSubmitting(true);

    // Get user UUID from Supabase session, or null if not logged in
    let userId = null;
    try {
      const { data: { session } } = await supabase.auth.getSession();
      userId = session?.user?.id || null;
    } catch (error) {
      console.warn('Unable to get user session for vote', error);
      userId = null;
    }

    const backendVoteValue = voteValue === 0 ? -1 : 1;

    // Create dummy vote data immediately
    const dummyVoteData = {
      id: `vote-${Date.now()}`,
      user_id: userId,
      song: activeSong,
      vote_value: backendVoteValue, // -1 for thumbs down, 1 for thumbs up
      vote_time: new Date().toISOString(),
      nfctagid: nfctagid || null,
      //client_vote_value: voteValue,
    };

    // Simulate API call (non-blocking, just logs to console)
    simulateApiCall(dummyVoteData, nfctagid);

    // Store dummy vote in localStorage for testing
    const existingVotes = JSON.parse(localStorage.getItem('dummyVotes') || '[]');
    existingVotes.push(dummyVoteData);
    localStorage.setItem('dummyVotes', JSON.stringify(existingVotes));

    console.log('Dummy vote submitted:', dummyVoteData);

    setHasVoted(true);
    setIsSubmitting(false);

    // Set flag in sessionStorage to allow access to confirmation page
    sessionStorage.setItem('voteSubmitted', 'true');
    sessionStorage.setItem('voteValue', voteValue.toString());
    sessionStorage.setItem('voteSong', activeSong);
    
    // Clear URL parameters immediately
    setSearchParams({});
    
    // Navigate to confirmation page immediately (no delay)
    navigate(`/vote/${voteValue}`, { 
      state: { song: activeSong, voteValue, nfctagid } 
    });
  };

  // Handle NFC tag scanning via URL parameters
  useEffect(() => {
    const voteValueParam = searchParams.get('voteValue');
    const nfctagid = searchParams.get('nfctagid');

    // If NFC tag ID is provided, use it to determine vote value
    if (nfctagid && NFC_TAG_MAPPING[nfctagid] !== undefined) {
      const voteValue = NFC_TAG_MAPPING[nfctagid];
      console.log(`NFC Tag detected: ${nfctagid} → Vote Value: ${voteValue}`);
      setNfcTagDetected(nfctagid);
      
      // Auto-submit vote when NFC tag is detected (no need to wait for songName - it's already set)
      if (!hasVoted && !isSubmitting) {
        handleVoteFromNFC(voteValue, nfctagid);
      }
    } 
    // If voteValue is provided directly in URL
    else if (voteValueParam && (voteValueParam === '0' || voteValueParam === '1')) {
      const voteValue = parseInt(voteValueParam, 10);
      console.log(`Vote value from URL: ${voteValue}`);
      
      if (!hasVoted && !isSubmitting) {
        handleVoteFromNFC(voteValue, nfctagid || 'direct-url');
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, hasVoted, isSubmitting]);

  const handleVote = (voteValue) => {
    handleVoteFromNFC(voteValue, null);
  };

  useEffect(() => {
    if (!isAccountMenuOpen) {
      return undefined;
    }

    const handleClickOutside = (event) => {
      if (accountMenuRef.current && !accountMenuRef.current.contains(event.target)) {
        setIsAccountMenuOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setIsAccountMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isAccountMenuOpen]);

  const handleSignOut = async () => {
    try {
      await supabase.auth.signOut();
    } catch (error) {
      console.error('Error signing out:', error);
    } finally {
      setIsAccountMenuOpen(false);
      navigate('/login');
    }
  };

  return (
    <div className={styles['voting-page']}>
      {isEasterEggActive && (
        <div className={styles['easter-egg-overlay']}>
          <div className={styles['easter-egg-backdrop']}></div>
          <div className={styles['easter-egg-orbital']}>
            <div className={styles['easter-egg-rings']}>
              <span></span>
              <span></span>
              <span></span>
            </div>
            <img src={easterEggImage} alt="Hidden sound guy" className={styles['easter-egg-image']} />
            <div className={styles['easter-egg-shine']}></div>
            <div className={styles['easter-egg-sparkles']}>
              {Array.from({ length: 8 }).map((_, index) => (
                <span key={index}></span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Animated Background Particles */}
      <div className={styles['particle-field']}>
        {[...Array(15)].map((_, i) => (
          <div key={i} className={styles['particle']} style={{
            '--delay': `${i * 0.08}s`,
            '--duration': `${4 + (i % 4)}s`,
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

      {/* Sound Wave Ripples around Record Player */}
      <div className={styles['sound-waves']}>
        <div className={styles['wave']}></div>
        <div className={styles['wave']}></div>
        <div className={styles['wave']}></div>
      </div>

      <div className={styles['voting-container']}>
        <div className={styles['header-row']}>
          <div className={styles['header-spacer']}></div>
          <div className={styles['account-wrapper']} ref={accountMenuRef}>
            <button
              type="button"
              className={styles['account-button']}
              onClick={() => setIsAccountMenuOpen((prev) => !prev)}
              aria-expanded={isAccountMenuOpen}
              aria-label="User menu"
            >
              <User size={22} />
            </button>
            {isAccountMenuOpen && (
              <div className={styles['account-dropdown']}>
                <button type="button" onClick={handleSignOut} className={styles['account-action']}>
                  <LogOut size={18} />
                  <span>Sign out</span>
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Header */}
        <div className={styles['voting-header']}>
          <div className={styles['voting-title-line']}></div>
          <h1 className={styles['voting-title']}>
            <span className={styles['title-word']}>Welcome </span>
            <span className={styles['title-word']}>to </span>
            <span className={styles['title-word']}>Sound </span>
            <span className={styles['title-word']}>Guys</span>
          </h1>
          <div className={styles['voting-title-line']}></div>
        </div>

        {/* Currently Playing Card with Record Player */}
        <div className={styles['song-card-container']}>
          <div className={styles['song-card']}>
            <div className={styles['card-glow']}></div>
            <div className={styles['song-label']}>
              <div className={styles['song-indicator']}></div>
              <p className={styles['song-label-text']}>
                Currently Playing
              </p>
            </div>
            <div className={styles['song-divider']}></div>
            
            {/* 3D Record Player */}
            <div className={styles['record-player-wrapper']}>
              <div className={styles['record-player-base']}>
                {/* Turntable platter */}
                <div className={styles['turntable-platter']}>
                  {/* Spinning vinyl record */}
                  <div className={styles['vinyl-record']}>
                    {/* Record grooves */}
                    <div className={styles['record-grooves']}>
                      <div className={styles['groove']}></div>
                      <div className={styles['groove']}></div>
                      <div className={styles['groove']}></div>
                      <div className={styles['groove']}></div>
                      <div className={styles['groove']}></div>
                    </div>
                    {/* Light reflections */}
                    <div className={styles['record-reflection']}></div>
                    <div className={styles['record-reflection-2']}></div>

                    {/* Center label with spinning gradient */}
                    <div className={styles['record-center']}>
                      <div className={styles['record-center-gradient']}></div>
                      <div className={styles['record-center-hole']}></div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            {/* Song name below record player */}
            <p className={styles['song-name']}>
              {currentSong}
            </p>
          </div>
        </div>

        {/* Rating Section - Only show on web */}
        {!isMobile && (
          <>
            <div className={styles['rating-section']}>
              <p className={styles['rating-prompt']}>
                <span className={styles['prompt-word']}>Rate</span>
                <span className={styles['prompt-word']}>the</span>
                <span className={styles['prompt-word']}>song</span>
                <span className={styles['prompt-word']}>that's</span>
                <span className={styles['prompt-word']}>playing</span>
                <span className={styles['prompt-word']}>now</span>
              </p>
            </div>

            {/* Thumbs Up/Down Buttons - Web only */}
            <div className={styles['vote-buttons-container']}>
              <button
                onClick={() => handleVote(0)}
                disabled={hasVoted || isSubmitting}
                className={`
                  ${styles['thumbs-button']} ${styles['thumbs-down']}
                  ${selectedVote === 0 ? styles.selected : ''}
                  ${hasVoted ? styles['vote-button-disabled'] : ''}
                `}
              >
                <div className={styles['button-icon-wrapper']}>
                  <ThumbsDown size={48} />
                </div>
                <div className={styles['button-shine']}></div>
              </button>
              
              <button
                onClick={() => handleVote(1)}
                disabled={hasVoted || isSubmitting}
                className={`
                  ${styles['thumbs-button']} ${styles['thumbs-up']}
                  ${selectedVote === 1 ? styles.selected : ''}
                  ${hasVoted ? styles['vote-button-disabled'] : ''}
                `}
              >
                <div className={styles['button-icon-wrapper']}>
                  <ThumbsUp size={48} />
                </div>
                <div className={styles['button-shine']}></div>
              </button>
            </div>
          </>
        )}

        {/* Mobile message */}
        {isMobile && (
          <div className={styles['mobile-message']}>
            <p className={styles['mobile-text']}>
              Use NFC stickers to vote
            </p>
            {nfcTagDetected && (
              <div className={styles['nfc-status']}>
                <p className={styles['nfc-status-text']}>
                  NFC Tag {nfcTagDetected} detected
                </p>
              </div>
            )}
          </div>
        )}

        {/* Status Messages */}
        {isSubmitting && (
          <div className={styles['status-container']}>
            <div className={styles['status-loading']}>
              <div className={styles['status-spinner']}></div>
              <p className={styles['status-loading-text']}>
                Submitting your vote...
              </p>
            </div>
          </div>
        )}

        {isLoadingSong && (
          <div className={styles['status-container']}>
            <div className={styles['status-loading']} style={{color: '#6b7280'}}>
              <div className={styles['status-spinner']}></div>
              <p className={styles['status-loading-text']}>
                Loading song information...
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Vote;

