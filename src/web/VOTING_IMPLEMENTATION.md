# Voting Page Implementation

## Overview
This document describes the voting functionality that has been implemented for the Sound Guys web application.

## Changes Made

### 1. Login Page (`src/Pages/Login.jsx`)
- **Redesigned** with a modern gradient background (purple-pink-red)
- Added a music note icon
- Enhanced button styling with hover effects and animations
- Improved overall visual appeal with glassmorphism effects

### 2. Voting Page (`src/Pages/Home.jsx`)
The home page has been transformed into a voting page with the following features:

#### Features:
- **Current Song Display**: Shows "Frog Noises" as the display name
- **1-5 Rating Buttons**: Large, clickable buttons styled like the reference image
- **Vote Submission**: Votes are sent to the Supabase `vote` table with:
  - `user_id`: UUID from authenticated user
  - `song`: "cat" (default value as requested)
  - `vote_value`: Selected rating (1-5)
  - `vote_time`: ISO timestamp of the vote
- **Vote Prevention**: Once voted, buttons are disabled until the next song
- **Visual Feedback**: 
  - Selected button turns green with shadow effect
  - Buttons are grayed out after voting
  - Loading state while submitting

#### Database Schema
The voting data is inserted into the `vote` table with the following structure:
```
vote
├── id (uuid, primary key)
├── user_id (uuid)
├── song (text)
├── vote_value (int4)
└── vote_time (timestamptz)
```

## Testing

### Prerequisites:
1. Ensure you have a `.env` file in `src/web/` with:
   ```
   VITE_SUPABASE_URL=your_supabase_project_url
   VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
   ```

2. Ensure your Supabase database has the `vote` table configured with proper Row Level Security policies that allow authenticated users to insert votes.

### To Test:
1. Run `npm run dev` in the `src/web` directory
2. Navigate to the login page
3. Sign in with Google OAuth
4. You should be redirected to the voting page
5. Click on any rating button (1-5)
6. Check your Supabase database to verify the vote was recorded with:
   - Your user UUID
   - Song name: "cat"
   - The vote value you selected
   - A timestamp

## Next Steps

### For Production:
- Replace the default song name "cat" with actual song data from your backend
- Implement a system to detect when a new song starts playing
- Reset the `hasVoted` state when a new song begins
- Consider adding a real-time listener to sync with the audio player
- Add animations for better user experience
- Consider adding a progress bar showing song duration

### Supabase Configuration:
Ensure your Supabase `vote` table has appropriate RLS policies:

```sql
-- Allow authenticated users to insert their own votes
CREATE POLICY "Users can insert their own votes"
ON vote FOR INSERT
TO authenticated
WITH CHECK (auth.uid() = user_id);

-- Allow users to view their own votes
CREATE POLICY "Users can view their own votes"
ON vote FOR SELECT
TO authenticated
USING (auth.uid() = user_id);
```

## Design Notes
- The voting page follows the design reference provided, with a dark gradient background
- Buttons are styled to match the gray boxes in the reference image
- The layout is responsive and centered
- Font choices use serif for the header and sans-serif for other text to match the elegant design

