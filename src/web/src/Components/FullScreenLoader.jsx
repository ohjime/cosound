import { useMemo } from 'react';
import styles from '../Pages/AuthCallback.module.css';

const PARTICLE_COUNT = 15;
const NOTE_SEQUENCE = ['♪', '♫', '♪', '♫'];
const VISUALIZER_BARS = 7;

const generateParticles = () =>
  Array.from({ length: PARTICLE_COUNT }).map((_, index) => ({
    key: index,
    delay: `${index * 0.12}s`,
    duration: `${3 + (index % 3)}s`,
    x: `${Math.random() * 100}%`,
    y: `${Math.random() * 100}%`,
  }));

const FullScreenLoader = ({ message = 'Compiling your favourites...' }) => {
  const particles = useMemo(generateParticles, []);

  return (
    <div className={styles['loading-page']}>
      <div className={styles['particle-field']}>
        {particles.map((particle) => (
          <div
            key={particle.key}
            className={styles['particle']}
            style={{
              '--delay': particle.delay,
              '--duration': particle.duration,
              '--x': particle.x,
              '--y': particle.y,
            }}
          ></div>
        ))}
      </div>

      <div className={styles['background-blobs']}>
        <div className={`${styles.blob} ${styles['blob-1']}`}></div>
        <div className={`${styles.blob} ${styles['blob-2']}`}></div>
        <div className={`${styles.blob} ${styles['blob-3']}`}></div>
      </div>

      <div className={styles['pulse-rings']}>
        <div className={styles['pulse-ring']}></div>
        <div className={styles['pulse-ring']}></div>
      </div>

      <div className={styles['loading-container']}>
        <div className={styles['sound-visualizer']}>
          {Array.from({ length: VISUALIZER_BARS }).map((_, index) => (
            <div key={index} className={styles['wave-bar']}></div>
          ))}
        </div>

        <div className={styles['music-notes']}>
          {NOTE_SEQUENCE.map((note, index) => (
            <span key={index} className={styles['music-note']}>
              {note}
            </span>
          ))}
        </div>

        <p className={styles['status-text']}>{message}</p>
      </div>
    </div>
  );
};

export default FullScreenLoader;

