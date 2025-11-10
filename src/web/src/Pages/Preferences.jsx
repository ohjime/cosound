import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import FullScreenLoader from '../Components/FullScreenLoader';
import styles from './Preferences.module.css';

const Preferences = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [genres, setGenres] = useState([]);
  const [isThinking, setIsThinking] = useState(true);

  useEffect(() => {
    const hasCompleted = localStorage.getItem('hasCompletedPreferences') === 'true';
    if (hasCompleted && !location.state?.forcePreferences) {
      navigate('/vote', { replace: true });
    }
  }, [location.state, navigate]);

  useEffect(() => {
    const stateGenres = location.state?.topGenres;
    const storedGenres = sessionStorage.getItem('topGenres');
    const resolvedGenres = stateGenres && Array.isArray(stateGenres)
      ? stateGenres
      : storedGenres
        ? JSON.parse(storedGenres)
        : [];

    setGenres(resolvedGenres);

    const timer = setTimeout(() => {
      setIsThinking(false);
    }, 1800);

    return () => clearTimeout(timer);
  }, [location.state]);

  const handleNext = () => {
    navigate('/preferences/0');
  };

  const handleSkip = () => {
    localStorage.setItem('hasCompletedPreferences', 'true');
    sessionStorage.removeItem('preferenceRatings');
    sessionStorage.removeItem('topGenres');
    navigate('/vote', { replace: true });
  };

  if (isThinking) {
    return <FullScreenLoader message="Compiling your favourites..." />;
  }

  return (
    <div className={styles['preferences-page']}>
      <div className={styles['preferences-background']}>
        <div className={`${styles.glow} ${styles['glow-1']}`}></div>
        <div className={`${styles.glow} ${styles['glow-2']}`}></div>
      </div>

      <div className={styles['preferences-card']}>
        <div className={styles['card-header']}>
          <span className={styles['card-pill']}>Step 1 of 6</span>
          <h1 className={styles['card-title']}>Your personalized palette</h1>
          <p className={styles['card-subtitle']}>
            Based on your Spotify vibes, here’s what you’ve been listening to the most lately.
          </p>
        </div>

        <div className={styles['genre-list']}>
          {genres.length > 0 ? (
            genres.map((genre, index) => (
              <div key={genre || index} className={styles['genre-item']}>
                <p className={styles['genre-name']}>{genre || 'Unknown'}</p>
              </div>
            ))
          ) : (
            <div className={styles['genre-empty']}>
              <p>We couldn’t retrieve your top genres yet, but let’s move on to personalize things manually.</p>
            </div>
          )}
        </div>

        <div className={styles['card-footer']}>
          <button onClick={handleSkip} className={styles['skip-button']}>
            Skip survey
          </button>
          <button onClick={handleNext} className={styles['next-button']}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
};

export default Preferences;

