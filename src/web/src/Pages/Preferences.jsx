import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';
import { useNavigate } from 'react-router-dom';

// Random music genres/preferences
const MUSIC_PREFERENCES = [
  'Pop', 'Rock', 'Jazz', 'Classical', 'Hip Hop', 'R&B',
  'Country', 'Electronic', 'Indie', 'Metal', 'Reggae', 'Blues',
  'Folk', 'Latin', 'K-Pop', 'Soul', 'Punk', 'Disco',
  'Funk', 'Alternative', 'Gospel', 'Techno', 'House', 'Trap'
];

const Preferences = () => {
  const [user, setUser] = useState(null);
  const [preferences, setPreferences] = useState([]);
  const [ratings, setRatings] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const navigate = useNavigate();

  // Generate 4 random preferences on mount
  useEffect(() => {
    const shuffled = [...MUSIC_PREFERENCES].sort(() => Math.random() - 0.5);
    const selected = shuffled.slice(0, 4);
    setPreferences(selected);
    
    // Initialize ratings object
    const initialRatings = {};
    selected.forEach((pref, index) => {
      initialRatings[index] = 0;
    });
    setRatings(initialRatings);
  }, []);

  useEffect(() => {
    // Get current user
    supabase.auth.getUser().then(({ data: { user } }) => {
      setUser(user);
    });
  }, []);

  const handleRatingChange = (index, rating) => {
    console.log('Setting rating:', rating, 'for index:', index);
    setRatings(prev => ({
      ...prev,
      [index]: rating
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!user) {
      setError('You must be logged in to save preferences');
      return;
    }

    // Filter out preferences with no rating and format for database
    const validPreferences = preferences
      .map((pref, index) => ({
        preference: pref,
        rating: ratings[index]
      }))
      .filter(item => item.rating > 0);

    if (validPreferences.length === 0) {
      setError('Please rate at least one preference');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      // Create JSON payload
      const preferencesData = {
        user_id: user.id,
        timestamp: new Date().toISOString(),
        preferences: validPreferences.map(item => ({
          preference: `${item.preference} - ${item.rating}`,
          genre: item.preference,
          rating: item.rating
        }))
      };

      // Save to JSON file (in browser, we'll use localStorage or download)
      const jsonString = JSON.stringify(preferencesData, null, 2);
      console.log('Preferences JSON:', jsonString);
      
      // Store in localStorage as backup
      localStorage.setItem('user_preferences', jsonString);

      // Get Supabase URL and API key
      const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
      const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

      // First, delete existing preferences via REST API
      const deleteResponse = await fetch(
        `${supabaseUrl}/rest/v1/preferences?user_id=eq.${user.id}`,
        {
          method: 'DELETE',
          headers: {
            'apikey': supabaseKey,
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal'
          }
        }
      );

      if (!deleteResponse.ok && deleteResponse.status !== 404) {
        throw new Error('Failed to delete existing preferences');
      }

      // Insert new preferences via REST API
      const preferencesToInsert = validPreferences.map(item => ({
        user_id: user.id,
        preference: `${item.preference} - ${item.rating}`
      }));

      const insertResponse = await fetch(
        `${supabaseUrl}/rest/v1/preferences`,
        {
          method: 'POST',
          headers: {
            'apikey': supabaseKey,
            'Authorization': `Bearer ${supabaseKey}`,
            'Content-Type': 'application/json',
            'Prefer': 'return=minimal'
          },
          body: JSON.stringify(preferencesToInsert)
        }
      );

      if (!insertResponse.ok) {
        const errorData = await insertResponse.json();
        throw new Error(errorData.message || 'Failed to save preferences');
      }

      setSuccess(true);
      
      // Optional: Download JSON file
      const blob = new Blob([jsonString], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `preferences_${user.id}_${Date.now()}.json`;
      // Uncomment the next line if you want to auto-download
      // link.click();
      URL.revokeObjectURL(url);

      setTimeout(() => {
        navigate('/');
      }, 1500);
    } catch (err) {
      console.error('Error saving preferences:', err);
      setError(err.message || 'Failed to save preferences');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-pink-50 via-white to-pink-50 flex items-center justify-center p-8">
      <div className="max-w-3xl w-full">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-5xl font-serif text-gray-900 mb-4">
            Hi {user?.user_metadata?.name || 'User'}
          </h1>
          <p className="text-2xl font-serif text-gray-700 leading-relaxed">
            Let us know your music tastes<br />
            so we can play something you like
          </p>
        </div>

        {/* Preferences Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="bg-pink-50 rounded-2xl p-10 shadow-sm">
            <div className="space-y-8">
              {preferences.map((pref, index) => (
                <div key={index} className="flex items-center justify-between gap-8 py-2">
                  {/* Preference Label */}
                  <div className="flex-1 text-left">
                    <span className="text-2xl font-serif text-gray-800 font-medium">
                      {pref}
                    </span>
                  </div>
                  
                  {/* Rating Buttons */}
                  <div className="flex items-center gap-3">
                    {[1, 2, 3, 4, 5].map((ratingValue) => {
                      const isSelected = ratings[index] === ratingValue;
                      return (
                        <button
                          key={ratingValue}
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            console.log('Clicked rating:', ratingValue, 'for index:', index, 'current:', ratings[index]);
                            handleRatingChange(index, ratingValue);
                          }}
                          style={{
                            backgroundColor: isSelected ? '#ec4899' : 'white',
                            color: isSelected ? 'white' : '#9ca3af',
                            border: isSelected ? 'none' : '2px solid #e5e7eb',
                            transform: isSelected ? 'scale(1.1)' : 'scale(1)',
                          }}
                          className="w-14 h-14 text-xl font-bold rounded-lg transition-all duration-200 hover:scale-110 hover:border-pink-300 shadow-sm"
                        >
                          {ratingValue}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <div className="bg-red-50 border-2 border-red-200 rounded-xl p-4 text-center">
              <p className="text-red-600 font-medium">{error}</p>
            </div>
          )}

          {/* Success Message */}
          {success && (
            <div className="bg-green-50 border-2 border-green-200 rounded-xl p-4 text-center">
              <p className="text-green-600 font-medium">Preferences saved successfully! Redirecting...</p>
            </div>
          )}

          {/* Submit Button */}
          <div className="flex justify-center gap-4">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="px-8 py-4 text-lg font-serif text-gray-600 bg-white border-2 border-gray-300 rounded-xl hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className={`
                px-8 py-4 text-lg font-serif text-white rounded-xl
                transition-all duration-200 transform hover:scale-105
                ${
                  loading
                    ? 'bg-gray-400 cursor-not-allowed'
                    : 'bg-gradient-to-r from-pink-400 to-pink-500 hover:from-pink-500 hover:to-pink-600 shadow-lg'
                }
              `}
            >
              {loading ? 'Saving...' : 'Save Preferences'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Preferences;
