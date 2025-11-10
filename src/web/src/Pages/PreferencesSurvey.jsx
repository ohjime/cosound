import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Pause, Play } from 'lucide-react';
import FullScreenLoader from '../Components/FullScreenLoader';
import styles from './Preferences.module.css';

import rainSound from '../assets/rain_sounds.wav';
import waveSound from '../assets/wave_sounds.wav';
import thunderSound from '../assets/thunder_sound.wav';
import windSound from '../assets/wind_sound.wav';
import fireSound from '../assets/fire_sound.flac';

const TOTAL_SURVEYS = 5;
const VISUALIZER_BARS = 24;
const AUDIO_TRACKS = [
  {
    title: 'Rain',
    description: 'Gentle rainfall tapping softly across a midnight window.',
    src: rainSound,
  },
  {
    title: 'Sea Wave',
    description: 'Rolling tides breathing in and out of a quiet shoreline.',
    src: waveSound,
  },
  {
    title: 'Thunderstorm',
    description: 'Brooding clouds with distant rumbles of thunderous energy.',
    src: thunderSound,
  },
  {
    title: 'Wind',
    description: 'Cool night breezes weaving calm currents through tall grass.',
    src: windSound,
  },
  {
    title: 'Fire Crackling',
    description: 'Cozy embers and soft pops from a glowing fireside.',
    src: fireSound,
  },
];

const ratingOptions = [1, 2, 3, 4, 5];

const PreferencesSurvey = () => {
  const { step: stepParam } = useParams();
  const navigate = useNavigate();
  const audioRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const dataArrayRef = useRef(null);
  const sourceRef = useRef(null);
  const animationRef = useRef(null);
  const [selectedRating, setSelectedRating] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);
  const [visualizerValues, setVisualizerValues] = useState(() =>
    Array.from({ length: VISUALIZER_BARS }, () => 0)
  );

  const stepIndex = useMemo(() => {
    const parsed = Number(stepParam);
    return Number.isNaN(parsed) ? 0 : parsed;
  }, [stepParam]);

  const currentTrack = AUDIO_TRACKS[stepIndex % AUDIO_TRACKS.length];
  const isLastSurvey = stepIndex === TOTAL_SURVEYS - 1;

  useEffect(() => {
    if (stepIndex < 0 || stepIndex >= TOTAL_SURVEYS) {
      navigate('/preferences/0', { replace: true });
    }
  }, [stepIndex, navigate]);

  useEffect(() => {
    const stored = sessionStorage.getItem('preferenceRatings');
    if (stored) {
      const parsed = JSON.parse(stored);
      const existing = parsed?.[stepIndex];
      if (existing) {
        setSelectedRating(existing);
      } else {
        setSelectedRating(null);
      }
    } else {
      setSelectedRating(null);
    }
  }, [stepIndex]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) {
      return undefined;
    }

    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => {
      setIsPlaying(false);
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
      setVisualizerValues((prev) => prev.map(() => 0));
    };

    audio.addEventListener('play', handlePlay);
    audio.addEventListener('pause', handlePause);
    audio.addEventListener('ended', handlePause);

    audio.pause();
    audio.currentTime = 0;
    setIsPlaying(false);

    return () => {
      audio.removeEventListener('play', handlePlay);
      audio.removeEventListener('pause', handlePause);
      audio.removeEventListener('ended', handlePause);
    };
  }, [stepIndex]);

  const togglePlayback = async () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (audio.paused) {
      try {
        if (!audioContextRef.current) {
          const Context = window.AudioContext || window.webkitAudioContext;
          audioContextRef.current = new Context();
        }
        const audioContext = audioContextRef.current;
        if (audioContext?.state === 'suspended') {
          await audioContext.resume();
        }

        if (!sourceRef.current) {
          const analyser = audioContext.createAnalyser();
          analyser.fftSize = 512;
          analyser.smoothingTimeConstant = 0.85;

          const source = audioContext.createMediaElementSource(audio);
          source.connect(analyser);
          analyser.connect(audioContext.destination);

          sourceRef.current = source;
          analyserRef.current = analyser;
          dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount);
        }
      } catch (error) {
        console.warn('Audio context setup failed', error);
      }

      audio
        .play()
        .catch((error) => console.warn('Unable to play audio sample', error));
    } else {
      audio.pause();
    }
  };

  const handleRatingSelect = (value) => {
    setSelectedRating(value);
  };

  useEffect(() => {
    if (!isPlaying) {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
      setVisualizerValues((prev) => prev.map(() => 0));
      return;
    }

    const analyser = analyserRef.current;
    const dataArray = dataArrayRef.current;

    if (!analyser || !dataArray) {
      return;
    }

    const bufferLength = analyser.frequencyBinCount;
    const barChunkSize = Math.floor(bufferLength / VISUALIZER_BARS);

    const animate = () => {
      analyser.getByteFrequencyData(dataArray);

      const nextValues = Array.from({ length: VISUALIZER_BARS }, (_, index) => {
        const start = index * barChunkSize;
        let sum = 0;
        for (let i = 0; i < barChunkSize; i += 1) {
          sum += dataArray[start + i] || 0;
        }
        const average = sum / barChunkSize;
        return Number((average / 255).toFixed(3));
      });

      setVisualizerValues(nextValues);
      animationRef.current = requestAnimationFrame(animate);
    };

    animationRef.current = requestAnimationFrame(animate);

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
        animationRef.current = null;
      }
    };
  }, [isPlaying]);

  useEffect(() => {
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      if (audioContextRef.current) {
        audioContextRef.current.close().catch(() => {});
      }
      animationRef.current = null;
      dataArrayRef.current = null;
      analyserRef.current = null;
      sourceRef.current = null;
      audioContextRef.current = null;
    };
  }, []);

  const handleAdvance = () => {
    if (!selectedRating) {
      return;
    }

    const stored = sessionStorage.getItem('preferenceRatings');
    const ratings = stored ? JSON.parse(stored) : [];
    ratings[stepIndex] = selectedRating;
    sessionStorage.setItem('preferenceRatings', JSON.stringify(ratings));

    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      setIsPlaying(false);
    }

    if (isLastSurvey) {
      const normalized = ratings.slice(0, TOTAL_SURVEYS).map((value) => {
        const ratingValue = Number(value || 0);
        return Number((ratingValue / 5).toFixed(2));
      });
      console.log('Preference ratings (raw):', ratings.slice(0, TOTAL_SURVEYS));
      console.log('Preference ratings (normalized):', normalized);

      setIsCompleting(true);

      setTimeout(() => {
        sessionStorage.removeItem('preferenceRatings');
        sessionStorage.removeItem('topGenres');
        localStorage.setItem('hasCompletedPreferences', 'true');
        navigate('/vote', { replace: true });
      }, 1500);
      return;
    }

    navigate(`/preferences/${stepIndex + 1}`);
  };

  const handleSkipSurvey = () => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
    }
    sessionStorage.removeItem('preferenceRatings');
    sessionStorage.removeItem('topGenres');
    localStorage.setItem('hasCompletedPreferences', 'true');
    navigate('/vote', { replace: true });
  };

  if (isCompleting) {
    return <FullScreenLoader message="Compiling your favourites..." />;
  }

  if (stepIndex < 0 || stepIndex >= TOTAL_SURVEYS) {
    return null;
  }

  return (
    <div className={styles['survey-page']}>
      <div className={styles['survey-background']}>
        <div className={`${styles.spark} ${styles['spark-1']}`}></div>
        <div className={`${styles.spark} ${styles['spark-2']}`}></div>
      </div>

      <div className={styles['survey-card']}>
        <header className={styles['survey-header']}>
          <div className={styles['survey-progress']}>
            <span className={styles['progress-pill']}>Step {stepIndex + 2} of 6</span>
            <div className={styles['progress-track']}>
              <div
                className={styles['progress-bar']}
                style={{ width: `${((stepIndex + 1) / TOTAL_SURVEYS) * 100}%` }}
              ></div>
            </div>
          </div>
          <h2 className={styles['survey-title']}>{currentTrack.title}</h2>
          <p className={styles['survey-subtitle']}>{currentTrack.description}</p>
        </header>

        <div className={styles['survey-audio']}>
          <div className={`${styles['audio-visualizer']} ${isPlaying ? styles['visualizer-active'] : ''}`}>
            {visualizerValues.map((value, index) => (
              <span
                key={index}
                className={styles['visualizer-bar']}
                style={{ height: `${Math.max(value, 0.05) * 100}%` }}
              ></span>
            ))}
          </div>

          <div className={styles['audio-controls']}>
            <button onClick={togglePlayback} className={styles['play-button']} type="button">
              {isPlaying ? <Pause size={22} /> : <Play size={22} />}
            </button>
            <div className={styles['audio-meta']}>
              <p className={styles['audio-heading']}>Preview this sound</p>
              <p className={styles['audio-caption']}>Tap play and let the vibe build before rating.</p>
            </div>
          </div>
          <audio ref={audioRef} src={currentTrack.src}></audio>
        </div>

        <div className={styles['survey-rating']}>
          <p className={styles['rating-label']}>How much does this resonate with you?</p>
          <div className={styles['rating-options']}>
            {ratingOptions.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => handleRatingSelect(value)}
                className={`${styles['rating-button']} ${
                  selectedRating === value ? styles['rating-selected'] : ''
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </div>

        <footer className={styles['survey-footer']}>
          <button type="button" onClick={handleSkipSurvey} className={styles['survey-skip']}>
            Skip survey
          </button>
          <button
            type="button"
            onClick={handleAdvance}
            disabled={!selectedRating}
            className={styles['survey-next']}
          >
            {isLastSurvey ? 'Finish' : 'Next'}
          </button>
        </footer>
      </div>
    </div>
  );
};

export default PreferencesSurvey;
