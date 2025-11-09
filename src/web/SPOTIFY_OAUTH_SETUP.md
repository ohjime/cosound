# Spotify OAuth Setup Guide

## Supabase Dashboard Configuration

To enable Spotify OAuth with Supabase, you need to configure it in your Supabase dashboard:

1. **Go to Supabase Dashboard** → Your Project → Authentication → Providers
2. **Enable Spotify Provider**
3. **Enter Spotify Credentials:**
   - **Client ID:** `ef5609327c8d4a5690a4ee513292a335`
   - **Client Secret:** `572f9e10f27143bebfa5ed63b54ce801`
4. **Set Redirect URL:** `https://bjieozmcptbxgbvzpfyc.supabase.co/auth/v1/callback`
   - This should be configured in your Spotify App settings as well

## Spotify App Configuration

1. **Go to Spotify Developer Dashboard:** https://developer.spotify.com/dashboard
2. **Select your app** (or create a new one)
3. **Add Redirect URI:**
   - `https://bjieozmcptbxgbvzpfyc.supabase.co/auth/v1/callback`
4. **Save changes**

## How It Works

1. User clicks "Continue with Spotify" button
2. Supabase redirects to Spotify authorization
3. User authorizes the app
4. Spotify redirects to Supabase callback URL
5. Supabase processes OAuth and creates session
6. Supabase redirects to your app's `/auth/callback` route
7. App fetches user's top 5 genres from Spotify API
8. Genres are logged to console for preference testing

## Note on Provider Tokens

Supabase may not expose Spotify provider tokens client-side for security reasons. If the token is not available, you may need to:

1. Use Supabase Edge Functions to access provider tokens server-side
2. Or implement a separate Spotify OAuth flow if you need direct access to Spotify API

The current implementation tries multiple methods to access the provider token, but if it's not available, check the console logs for debugging information.

