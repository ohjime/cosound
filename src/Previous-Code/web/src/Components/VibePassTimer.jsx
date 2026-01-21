import { useState, useEffect } from 'react';
import { apiClient } from '../lib/apt';
import { Music2, Clock } from 'lucide-react';

export function VibePassTimer() {
  const [minutesLeft, setMinutesLeft] = useState(null);
  const [isExpanded, setIsExpanded] = useState(true);
  const [currentSong, setCurrentSong] = useState('Ocean Waves');
  const [sessionActive, setSessionActive] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Check session on mount and periodically
  useEffect(() => {
    const checkSession = async () => {
      try {
        console.log('🔍 VibeTimer: Checking session...');
        const result = await apiClient('/api/session');
        console.log('✅ VibeTimer: Session result:', result);
        
        if (result.active && result.data) {
          setMinutesLeft(result.data.minutes_remaining);
          setSessionActive(true);
          setError(null);
        } else {
          setSessionActive(false);
        }
        setIsLoading(false);
      } catch (err) {
        console.error('❌ Timer: API error:', err);
        setError(err.message || 'Failed to load session');
        setSessionActive(false);
        setIsLoading(false);
      }
    };

    checkSession();
    
    // Recheck every 30 seconds
    const interval = setInterval(checkSession, 30000);
    
    return () => clearInterval(interval);
  }, []);

  // Client-side countdown (updates every minute)
  useEffect(() => {
    if (!sessionActive || minutesLeft === null || minutesLeft <= 0) {
      return;
    }

    const interval = setInterval(() => {
      setMinutesLeft((prev) => {
        if (prev && prev > 0) {
          return prev - 1;
        }
        setSessionActive(false);
        return 0;
      });
    }, 60000);

    return () => clearInterval(interval);
  }, [sessionActive, minutesLeft]);

  // Auto-collapse after 4 seconds
  useEffect(() => {
    if (isExpanded && sessionActive) {
      const timer = setTimeout(() => {
        setIsExpanded(false);
      }, 4000);
      
      return () => clearTimeout(timer);
    }
  }, [isExpanded, sessionActive]);

  // Don't show if loading or no session
  if (isLoading) {
    return null;
  }

  if (error) {
    return null;
  }

  if (!sessionActive || minutesLeft === null) {
    return null;
  }

  // Progress calculation
  const progress = ((60 - minutesLeft) / 60) * 100;

  return (
    <>
      {/* EXPANDED - Big Center Display */}
      {isExpanded && (
        <div
          onClick={() => setIsExpanded(false)}
          className="fixed inset-0 z-[9999] flex items-center justify-center 
                     bg-black/60 backdrop-blur-sm
                     animate-in fade-in duration-300"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-[90%] max-w-sm
                       bg-gradient-to-br from-slate-900/95 via-purple-900/90 to-slate-900/95
                       backdrop-blur-xl
                       border border-white/10
                       rounded-3xl
                       shadow-2xl shadow-purple-500/20
                       p-8
                       animate-in zoom-in-95 slide-in-from-bottom-8 duration-500
                       relative overflow-hidden"
          >
            {/* Animated background gradient */}
            <div className="absolute inset-0 bg-gradient-to-br from-purple-600/10 via-transparent to-blue-600/10 
                            animate-pulse" />
            
            {/* Content */}
            <div className="relative z-10 space-y-6">
              {/* Header Badge */}
              <div className="flex justify-center">
                <div className="inline-flex items-center gap-2 px-4 py-2
                                bg-white/10 backdrop-blur-sm
                                border border-white/20
                                rounded-full">
                  <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                  <span className="text-xs font-bold text-white/80 uppercase tracking-widest">
                    Vibe Pass Active
                  </span>
                </div>
              </div>

              {/* Timer Circle */}
              <div className="relative w-48 h-48 mx-auto">
                {/* SVG Progress Circle */}
                <svg className="w-full h-full transform -rotate-90">
                  {/* Background */}
                  <circle
                    cx="96"
                    cy="96"
                    r="88"
                    fill="none"
                    stroke="rgba(255, 255, 255, 0.08)"
                    strokeWidth="10"
                  />
                  {/* Progress */}
                  <circle
                    cx="96"
                    cy="96"
                    r="88"
                    fill="none"
                    stroke="url(#timerGradient)"
                    strokeWidth="10"
                    strokeLinecap="round"
                    strokeDasharray={`${2 * Math.PI * 88}`}
                    strokeDashoffset={`${2 * Math.PI * 88 * (1 - progress / 100)}`}
                    className="transition-all duration-1000 ease-out"
                    style={{
                      filter: 'drop-shadow(0 0 12px rgba(139, 92, 246, 0.6))'
                    }}
                  />
                  <defs>
                    <linearGradient id="timerGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#a78bfa" />
                      <stop offset="50%" stopColor="#8b5cf6" />
                      <stop offset="100%" stopColor="#7c3aed" />
                    </linearGradient>
                  </defs>
                </svg>

                {/* Center Time */}
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <div className="text-7xl font-black bg-gradient-to-br from-white via-purple-100 to-purple-200 
                                  bg-clip-text text-transparent
                                  drop-shadow-2xl leading-none">
                    {minutesLeft}
                  </div>
                  <div className="text-sm font-bold text-white/60 uppercase tracking-wider mt-2">
                    minutes left
                  </div>
                </div>
              </div>

              {/* Divider */}
              <div className="h-px bg-gradient-to-r from-transparent via-white/20 to-transparent" />

              {/* Now Playing */}
              <div className="text-center space-y-3">
                <div className="flex items-center justify-center gap-2">
                  <Music2 className="w-4 h-4 text-purple-400" />
                  <span className="text-xs font-bold text-white/50 uppercase tracking-widest">
                    Now Playing
                  </span>
                </div>
                
                <div className="text-xl font-bold text-white drop-shadow-lg">
                  {currentSong}
                </div>

                {/* Audio Visualizer */}
                <div className="flex items-end justify-center gap-1.5 h-10 pt-2">
                  {[1, 2, 3, 4, 5, 6].map((i) => (
                    <div
                      key={i}
                      className="w-1 bg-gradient-to-t from-purple-500 via-purple-400 to-purple-300 
                                 rounded-full shadow-lg shadow-purple-500/50"
                      style={{
                        animation: `audioWave 0.8s ease-in-out ${i * 0.1}s infinite`
                      }}
                    />
                  ))}
                </div>
              </div>

              {/* Tap to minimize hint */}
              <div className="text-center">
                <p className="text-xs text-white/40 animate-pulse">
                  Tap anywhere to minimize
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* COLLAPSED - Clean Minimal Top Bar */}
      {!isExpanded && (
        <div
          onClick={() => setIsExpanded(true)}
          className="fixed top-4 left-4 z-9998
                     flex items-center gap-3
                     bg-slate-900/90 backdrop-blur-xl
                     border border-white/10
                     rounded-full
                     pl-3 pr-4 py-2
                     shadow-xl shadow-purple-500/10
                     cursor-pointer
                     transition-all duration-500
                     hover:shadow-2xl hover:shadow-purple-500/20
                     hover:scale-[1.02]
                     active:scale-95
                     animate-in slide-in-from-left-8 fade-in duration-500"
        >
          {/* Music Icon with pulse */}
          <div className="relative flex-shrink-0">
            <div className="w-8 h-8 rounded-full bg-purple-500/20 flex items-center justify-center">
              <Music2 className="w-4 h-4 text-purple-400" />
            </div>
            <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-green-400 rounded-full 
                            animate-pulse shadow-lg shadow-green-400/50" />
          </div>

          {/* Song Name */}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white truncate">
              {currentSong}
            </p>
          </div>

          {/* Timer */}
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <Clock className="w-3.5 h-3.5 text-purple-400" />
            <span className="text-base font-bold text-white tabular-nums">
              {minutesLeft}
            </span>
            <span className="text-[10px] text-white/50 uppercase">
              min
            </span>
          </div>
        </div>
      )}
    </>
  );
}