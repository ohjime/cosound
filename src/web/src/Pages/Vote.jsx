import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import styles from './Vote.module.css';

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

  const [currentSong, setCurrentSong] = useState('Frog Noises');
  const [selectedVote, setSelectedVote] = useState(null);
  const [hasVoted, setHasVoted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [songId, setSongId] = useState(null);
  const [songName, setSongName] = useState(null);
  const [isLoadingSong, setIsLoadingSong] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [nfcTagDetected, setNfcTagDetected] = useState(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

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
    // Simulate loading song data with dummy data
    const loadDummySong = () => {
      setIsLoadingSong(true);
      // Simulate a small delay
      setTimeout(() => {
        const randomSong = DUMMY_SONGS[Math.floor(Math.random() * DUMMY_SONGS.length)];
        setSongId(randomSong.id);
        setSongName(randomSong.song);
        setCurrentSong(randomSong.song);
        setIsLoadingSong(false);
      }, 500);
    };

    loadDummySong();
  }, []);

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
    if (hasVoted || isSubmitting || !songName) {
      return;
    }

    setSelectedVote(voteValue);
    setIsSubmitting(true);

    // Simulate API call delay with dummy data
    setTimeout(async () => {
      // Create dummy vote data
      const dummyVoteData = {
        id: `vote-${Date.now()}`,
        user_id: 'dummy-user-id',
        song: songName,
        vote_value: voteValue, // 0 for thumbs down, 1 for thumbs up
        vote_time: new Date().toISOString(),
        nfctagid: nfctagid || null,
      };

      // Simulate API call
      await simulateApiCall(dummyVoteData, nfctagid);

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
      sessionStorage.setItem('voteSong', currentSong);
      
      // Clear URL parameters
      setSearchParams({});
      
      // Navigate to confirmation page
      navigate(`/vote/${voteValue}`, { 
        state: { song: currentSong, voteValue, nfctagid } 
      });
    }, 800); // Simulate 800ms API delay
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
      
      // Auto-submit vote when NFC tag is detected
      if (!hasVoted && !isSubmitting && songName) {
        handleVoteFromNFC(voteValue, nfctagid);
      }
    } 
    // If voteValue is provided directly in URL
    else if (voteValueParam && (voteValueParam === '0' || voteValueParam === '1')) {
      const voteValue = parseInt(voteValueParam, 10);
      console.log(`Vote value from URL: ${voteValue}`);
      
      if (!hasVoted && !isSubmitting && songName) {
        handleVoteFromNFC(voteValue, nfctagid || 'direct-url');
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, songName, hasVoted, isSubmitting]);

  const handleVote = async (voteValue) => {
    await handleVoteFromNFC(voteValue, null);
  };

  return (
    <div className={styles['voting-page']}>
      {/* Decorative background elements */}
      <div className={styles['background-blobs']}>
        <div className={`${styles.blob} ${styles['blob-1']}`}></div>
        <div className={`${styles.blob} ${styles['blob-2']}`}></div>
        <div className={`${styles.blob} ${styles['blob-3']}`}></div>
      </div>

      <div className={styles['voting-container']}>
        {/* Header */}
        <div className={styles['voting-header']}>
          <div className={styles['voting-title-line']}></div>
          <h1 className={styles['voting-title']}>
            Welcome to Sound Guys
          </h1>
          <div className={styles['voting-title-line']} style={{background: 'linear-gradient(to right, #ec4899, #a855f7)'}}></div>
        </div>

        {/* Currently Playing Card */}
        <div className={styles['song-card-container']}>
          <div className={styles['song-card']}>
            <div className={styles['song-label']}>
              <div className={styles['song-indicator']}></div>
              <p className={styles['song-label-text']}>
                Currently Playing
              </p>
            </div>
            <div className={styles['song-divider']}></div>
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
                Rate the song that's playing now
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
                <ThumbsDown size={48} />
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
                <ThumbsUp size={48} />
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

