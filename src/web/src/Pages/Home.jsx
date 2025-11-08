import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import styles from './Home.module.css';

const Home = () => {
  const [user, setUser] = useState(null);
  const [currentSong, setCurrentSong] = useState('Frog Noises');
  const [selectedVote, setSelectedVote] = useState(null);
  const [hasVoted, setHasVoted] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [songId, setSongId] = useState(null);
  const [songName, setSongName] = useState(null);

  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      setUser(user);
    });

    // Fetch song from songs table - try "cat" first, then any available song
    const fetchSong = async () => {
      try {
        // First try to find a song named "cat"
        let { data, error } = await supabase
          .from('songs')
          .select('id, song')
          .eq('song', 'cat')
          .limit(1)
          .single();

        // If "cat" doesn't exist, get the first available song
        if (error || !data) {
          const { data: songsData, error: songsError } = await supabase
            .from('songs')
            .select('id, song')
            .limit(1)
            .single();

          if (!songsError && songsData) {
            setSongId(songsData.id); // Store UUID
            setSongName(songsData.song); // Store name for display
            setCurrentSong(songsData.song);
          }
        } else {
          setSongId(data.id); // Store UUID
          setSongName(data.song); // Store name for display
          setCurrentSong(data.song);
        }
      } catch (err) {
        console.error('Error fetching song:', err);
        // If query fails, we'll handle the error when voting
      }
    };

    fetchSong();
  }, []);

  const handleVote = async (voteValue) => {
    if (hasVoted || isSubmitting || !user || (!songId && !songName)) return;

    setSelectedVote(voteValue);
    setIsSubmitting(true);

    try {
      // Try with song name first (since vote.song is text type)
      let songValue = songName || songId;
      let { error } = await supabase
        .from('vote')
        .insert([
          {
            user_id: user.id,
            song: songValue,
            vote_value: voteValue,
            vote_time: new Date().toISOString(),
          },
        ]);

      // If FK error and we tried name, try with song ID instead
      if (error && error.message.includes('foreign key') && songName && songId) {
        const { error: idError } = await supabase
          .from('vote')
          .insert([
            {
              user_id: user.id,
              song: songId.toString(), // Try song ID as string
              vote_value: voteValue,
              vote_time: new Date().toISOString(),
            },
          ]);

        if (idError) {
          throw idError;
        }
      } else if (error) {
        throw error;
      }

      setHasVoted(true);
    } catch (error) {
      console.error('Error submitting vote:', error);
      alert('Error submitting vote: ' + error.message);
      setSelectedVote(null);
    } finally {
      setIsSubmitting(false);
    }
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
        {/* Header with elegant styling */}
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

        {/* Rating Section */}
        <div className={styles['rating-section']}>
          <p className={styles['rating-prompt']}>
            Rate the song that's playing now
          </p>
        </div>

        {/* Vote Buttons with enhanced design */}
        <div className={styles['vote-buttons-container']}>
          {[1, 2, 3, 4, 5].map((value, index) => (
            <button
              key={value}
              onClick={() => handleVote(value)}
              disabled={hasVoted || isSubmitting || (!songId && !songName)}
              style={{ animationDelay: `${index * 100}ms` }}
              className={`
                ${styles['vote-button']} ${styles['fade-in-up']}
                ${selectedVote === value ? styles.selected : ''}
                ${hasVoted ? styles['vote-button-disabled'] : ''}
              `}
            >
              {value}
            </button>
          ))}
        </div>

        {/* Status Messages with animations */}
        {hasVoted && (
          <div className={`${styles['status-container']} ${styles['fade-in']}`}>
            <div className={styles['status-success']}>
              <svg className={styles['status-success-icon']} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <p className={styles['status-success-text']}>
                Thank you for voting! Wait for the next song to vote again.
              </p>
            </div>
          </div>
        )}

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

        {!songId && !songName && (
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

export default Home;
