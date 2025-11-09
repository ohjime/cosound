import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import styles from './AuthCallback.module.css';

// Function to fetch user's top 5 genres from Spotify
const fetchTopGenres = async (accessToken) => {
  try {
    // Fetch top artists from Spotify API
    const response = await fetch('https://api.spotify.com/v1/me/top/artists?limit=50&time_range=medium_term', {
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`Spotify API error: ${response.status}`);
    }

    const data = await response.json();
    const artists = data.items || [];

    // Extract all genres from top artists
    const genreCounts = {};
    artists.forEach(artist => {
      if (artist.genres && Array.isArray(artist.genres)) {
        artist.genres.forEach(genre => {
          genreCounts[genre] = (genreCounts[genre] || 0) + 1;
        });
      }
    });

    // Sort genres by count and get top 5
    const topGenres = Object.entries(genreCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([genre]) => genre);

    return topGenres;
  } catch (error) {
    console.error('Error fetching Spotify genres:', error);
    return [];
  }
};

export const AuthCallback = () => {
  const navigate = useNavigate();
  const [status, setStatus] = useState('Authenticating...');

  useEffect(() => {
    const handleAuth = async () => {
      try {
        // Get the session after OAuth redirect
        const { data: { session }, error: sessionError } = await supabase.auth.getSession();
        
        if (sessionError) {
          console.error('Session error:', sessionError);
          navigate('/login');
          return;
        }

        if (session) {
          setStatus('Fetching your music preferences...');
          
          // Try multiple methods to get Spotify access token
          let spotifyToken = null;
          
          // Method 1: Check session provider_token
          if (session.provider_token) {
            spotifyToken = session.provider_token;
          }
          // Method 2: Check user metadata (Supabase might store it here)
          else if (session.user?.app_metadata?.provider_token) {
            spotifyToken = session.user.app_metadata.provider_token;
          }
          // Method 3: Try refreshing session to get provider token
          else {
            try {
              const { data: { session: refreshedSession } } = await supabase.auth.refreshSession();
              spotifyToken = refreshedSession?.provider_token || refreshedSession?.user?.app_metadata?.provider_token;
            } catch (refreshError) {
              console.log('Could not refresh session for provider token:', refreshError);
            }
          }
          
          // Method 4: Get user data which might contain provider token
          if (!spotifyToken) {
            try {
              const { data: { user } } = await supabase.auth.getUser();
              spotifyToken = user?.app_metadata?.provider_token;
            } catch (userError) {
              console.log('Could not get user for provider token:', userError);
            }
          }
          
          // If we have a Spotify token, fetch top genres
          if (spotifyToken) {
            const topGenres = await fetchTopGenres(spotifyToken);
            
            if (topGenres.length > 0) {
              console.log('=== USER TOP 5 SPOTIFY GENRES ===');
              topGenres.forEach((genre, index) => {
                console.log(`${index + 1}. ${genre}`);
              });
              console.log('===================================');
            } else {
              console.log('No genres found. User may not have enough listening history.');
            }
          } else {
            console.log('⚠️ Spotify access token not available.');
            console.log('This might be because:');
            console.log('1. Spotify OAuth provider is not configured in Supabase dashboard');
            console.log('2. Supabase does not expose provider tokens client-side');
            console.log('3. You may need to use Supabase Edge Functions to access provider tokens');
            console.log('Session data:', {
              hasProviderToken: !!session.provider_token,
              hasUserMetadata: !!session.user?.app_metadata,
              sessionKeys: Object.keys(session),
            });
          }
          
          // Show loading screen for a moment before redirecting
          setStatus('Welcome! Getting things ready for you');
          setTimeout(() => {
            navigate('/vote');
          }, 1500);
        } else {
          navigate('/login');
        }
      } catch (error) {
        console.error('Auth callback error:', error);
        navigate('/login');
      }
    };

    handleAuth();
  }, [navigate]);

  return (
    <div className={styles['loading-page']}>
      {/* Floating Particles */}
      <div className={styles['particle-field']}>
        {[...Array(15)].map((_, i) => (
          <div key={i} className={styles['particle']} style={{
            '--delay': `${i * 0.12}s`,
            '--duration': `${3 + (i % 3)}s`,
            '--x': `${Math.random() * 100}%`,
            '--y': `${Math.random() * 100}%`,
          }}></div>
        ))}
      </div>

      {/* Background Blobs */}
      <div className={styles['background-blobs']}>
        <div className={`${styles.blob} ${styles['blob-1']}`}></div>
        <div className={`${styles.blob} ${styles['blob-2']}`}></div>
        <div className={`${styles.blob} ${styles['blob-3']}`}></div>
      </div>

      {/* Pulsing Rings */}
      <div className={styles['pulse-rings']}>
        <div className={styles['pulse-ring']}></div>
        <div className={styles['pulse-ring']}></div>
      </div>

      <div className={styles['loading-container']}>
        {/* Sound Wave Visualizer */}
        <div className={styles['sound-visualizer']}>
          <div className={styles['wave-bar']}></div>
          <div className={styles['wave-bar']}></div>
          <div className={styles['wave-bar']}></div>
          <div className={styles['wave-bar']}></div>
          <div className={styles['wave-bar']}></div>
          <div className={styles['wave-bar']}></div>
          <div className={styles['wave-bar']}></div>
        </div>

        {/* Music Notes */}
        <div className={styles['music-notes']}>
          <span className={styles['music-note']}>♪</span>
          <span className={styles['music-note']}>♫</span>
          <span className={styles['music-note']}>♪</span>
          <span className={styles['music-note']}>♫</span>
        </div>

        {/* Status Text */}
        <p className={styles['status-text']}>{status}</p>
      </div>
    </div>
  );
};
