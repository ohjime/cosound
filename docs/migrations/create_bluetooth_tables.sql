-- ============================================
-- Bluetooth Presence Detection Tables
-- ============================================

-- 1. Create test_bt_devices table
CREATE TABLE IF NOT EXISTS test_bt_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    device_mac TEXT NOT NULL UNIQUE,
    device_name TEXT,
    status TEXT NOT NULL DEFAULT 'disconnected',
    last_seen TIMESTAMPTZ,
    grace_period_ends_at TIMESTAMPTZ,
    rssi INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Create test_bt_sessions table
CREATE TABLE IF NOT EXISTS test_bt_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    device_mac TEXT NOT NULL,
    device_name TEXT,
    connected_at TIMESTAMPTZ DEFAULT NOW(),
    disconnected_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_bt_devices_user_id ON test_bt_devices(user_id);
CREATE INDEX IF NOT EXISTS idx_bt_devices_status ON test_bt_devices(status);
CREATE INDEX IF NOT EXISTS idx_bt_devices_last_seen ON test_bt_devices(last_seen);
CREATE INDEX IF NOT EXISTS idx_bt_sessions_user_id ON test_bt_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_bt_sessions_status ON test_bt_sessions(status);

-- 4. Add comments
COMMENT ON TABLE test_bt_devices IS 'Bluetooth devices registered for presence detection';
COMMENT ON TABLE test_bt_sessions IS 'Bluetooth connection sessions tracking user presence';

-- 5. Enable Row Level Security (optional for POC)
ALTER TABLE test_bt_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_bt_sessions ENABLE ROW LEVEL SECURITY;

-- 6. Create permissive policies for testing (DISABLE IN PRODUCTION!)
CREATE POLICY "Allow all operations for testing" ON test_bt_devices
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all operations for testing" ON test_bt_sessions
    FOR ALL USING (true) WITH CHECK (true);

-- ============================================
-- Verification Queries
-- ============================================

-- Check tables exist
SELECT table_name, table_type 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('test_bt_devices', 'test_bt_sessions');

-- Check columns
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name IN ('test_bt_devices', 'test_bt_sessions')
ORDER BY table_name, ordinal_position;

-- ============================================
-- Test Insert (Optional)
-- ============================================

-- Insert test device
INSERT INTO test_bt_devices (user_id, device_mac, device_name, status)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    '50:E7:B7:36:79:A4',
    'PRANAV Phone',
    'disconnected'
);

-- Verify insert
SELECT * FROM test_bt_devices WHERE device_mac = '50:E7:B7:36:79:A4';
