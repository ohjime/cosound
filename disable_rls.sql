-- Disable Row Level Security for admin dashboard tables
-- Run this in Supabase SQL Editor

-- Disable RLS on test_bt_devices
ALTER TABLE test_bt_devices DISABLE ROW LEVEL SECURITY;

-- Disable RLS on test_bt_sessions
ALTER TABLE test_bt_sessions DISABLE ROW LEVEL SECURITY;

-- Verify RLS is disabled
SELECT 
  tablename, 
  rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
  AND tablename IN ('test_bt_devices', 'test_bt_sessions');
