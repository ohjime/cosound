import { supabase } from './supabase';

// Dynamically determine API URL based on current hostname
// Works for localhost and any IP address (mobile, teammates, etc.)
const getApiUrl = () => {
  const envApiUrl = import.meta.env.VITE_API_URL;

  // If env var is set and not localhost, use it (for production)
  if (envApiUrl && !envApiUrl.includes('localhost')) {
    return envApiUrl;
  }

  // For development: use current hostname with port 3000
  // localhost:5173 → localhost:3000
  // 10.0.0.51:5173 → 10.0.0.51:3000
  const protocol = window.location.protocol;
  const hostname = window.location.hostname;
  return `${protocol}//${hostname}:3000`;
};

const API_URL = getApiUrl();

export async function apiClient(endpoint, options = {}) {
  const { data: { session } } = await supabase.auth.getSession();

  const headers = {
    'Content-Type': 'application/json',
    ...(session?.access_token && {
      Authorization: `Bearer ${session.access_token}`,
    }),
    ...options.headers,
  };

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: 'Request failed' }));
    const errorMessage = error.error || 'Request failed';
    // Include status code in error for better handling
    const err = new Error(errorMessage);
    err.status = response.status;
    err.statusText = response.statusText;
    throw err;
  }

  return response.json();
}