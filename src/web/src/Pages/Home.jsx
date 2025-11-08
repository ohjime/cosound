import { useEffect, useState } from 'react';
import { supabase } from '../lib/supabase';

const Home = () => {
  const [user, setUser] = useState(null);

  useEffect(() => {
    supabase.auth.getUser().then(({ data: { user } }) => {
      setUser(user);
    });
  }, []);

  return (
    <div>
      <h1 className="text-3xl font-bold mb-6">Home</h1>

      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Welcome back!</h2>
        {user && (
          <div className="space-y-2">
            <p className="text-gray-600">Email: {user.email}</p>
          </div>
        )}
      </div>

 
    </div>
  );
};

export default Home;
