# Quick Start Guide - Testing the Voting Functionality

## Prerequisites
Make sure you have a `.env` file in the `src/web` directory with your Supabase credentials:
```
VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

## Database Setup
Ensure your Supabase `vote` table has the correct Row Level Security (RLS) policies:

```sql
-- Enable RLS on the vote table
ALTER TABLE vote ENABLE ROW LEVEL SECURITY;

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

## Running the App

1. Navigate to the web directory:
   ```bash
   cd src/web
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

3. Open your browser to the URL shown (usually `http://localhost:5173`)

## Testing the Voting Flow

1. **Login Page**: You'll see a modern gradient background with "Continue with Google" button
2. **Click** the Google sign-in button
3. **Authenticate** with your Google account
4. **You'll be redirected** to the voting page showing:
   - "Welcome to Sound Guys" header
   - "Currently Playing: Frog Noises"
   - Five rating buttons (1-5)

5. **Click any rating button** (1-5) to submit your vote
6. **The button will turn green** and you'll see a success message
7. **All buttons will be disabled** after voting

## Verify in Database

1. Go to your Supabase dashboard
2. Navigate to the Table Editor
3. Open the `vote` table
4. You should see a new row with:
   - `user_id`: Your user's UUID
   - `song`: "cat"
   - `vote_value`: The number you selected (1-5)
   - `vote_time`: The timestamp when you voted

## What's Next?

The current implementation uses a default song name of "cat" as requested. To make this fully functional:

1. **Integrate with your audio player** to get the actual song playing
2. **Implement song change detection** to reset voting when a new song plays
3. **Update the song parameter** in the vote submission to use the actual song name instead of "cat"

## Troubleshooting

### Vote doesn't submit:
- Check browser console for errors
- Verify Supabase credentials in `.env`
- Ensure RLS policies are set up correctly
- Check that you're authenticated (logged in)

### Can't see votes in database:
- Check RLS policies are configured
- Verify the table structure matches the schema
- Make sure you're looking at the correct Supabase project

### Login doesn't work:
- Verify Google OAuth is configured in Supabase
- Check redirect URLs are set up correctly in Supabase dashboard
- Ensure callback URL matches your app URL

