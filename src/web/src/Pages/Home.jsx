import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';

const Home = () => {
  const [user, setUser] = useState(null);
  const [rating, setRating] = useState(0);

  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      setUser(user);
    });
  }, []);

  const handleRating = (value) => {
    setRating(value);
    // You can add logic here to submit the rating to your backend
    console.log('User rated:', value);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-8">
      <div className="max-w-2xl w-full text-center space-y-12">
        {/* Welcome Header */}
        <h1 className="text-6xl font-serif italic text-gray-900">
          Welcome to Sound Guys
        </h1>

        {/* Currently Playing Section */}
        <div className="space-y-4">
          <h2 className="text-3xl font-serif text-gray-800">
            Currently Playing : <span className="text-green-600 italic">Frog Noises</span>
          </h2>
        </div>

        {/* Rating Section */}
        <div className="space-y-6">
          <h3 className="text-2xl font-serif italic text-gray-700">
            Rate the song that's playing now
          </h3>

          {/* Rating Buttons */}
          <div className="flex justify-center gap-4">
            {[1, 2, 3, 4, 5].map((num) => (
              <button
                key={num}
                onClick={() => handleRating(num)}
                className={`
                  w-20 h-20 text-3xl font-bold rounded-lg
                  transition-all duration-200 transform hover:scale-110
                  ${
                    rating === num
                      ? 'bg-gray-700 text-white shadow-xl scale-110'
                      : 'bg-gray-400 text-gray-800 hover:bg-gray-500'
                  }
                `}
              >
                {num}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Home;

