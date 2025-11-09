import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

const Home = () => {
  const navigate = useNavigate();

  useEffect(() => {
    // Redirect to vote page
    navigate('/vote', { replace: true });
  }, [navigate]);

  return null;
};

export default Home;

