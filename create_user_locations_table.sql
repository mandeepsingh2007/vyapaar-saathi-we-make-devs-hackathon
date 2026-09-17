-- Create user_locations table in Supabase
-- Run this SQL in your Supabase SQL Editor

CREATE TABLE IF NOT EXISTS user_locations (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    accuracy DOUBLE PRECISION,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on user_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_locations_user_id ON user_locations(user_id);

-- Add comment to table
COMMENT ON TABLE user_locations IS 'Stores GPS locations of shopkeepers for personalized supplier search';

-- Add comments to columns
COMMENT ON COLUMN user_locations.user_id IS 'WhatsApp user ID (e.g., whatsapp:+919876543210)';
COMMENT ON COLUMN user_locations.latitude IS 'GPS latitude coordinate';
COMMENT ON COLUMN user_locations.longitude IS 'GPS longitude coordinate';
COMMENT ON COLUMN user_locations.accuracy IS 'GPS accuracy in meters';
COMMENT ON COLUMN user_locations.updated_at IS 'Last time location was updated';
COMMENT ON COLUMN user_locations.created_at IS 'First time location was saved';

-- Enable Row Level Security (RLS)
ALTER TABLE user_locations ENABLE ROW LEVEL SECURITY;

-- Create policy to allow all operations (adjust based on your security needs)
CREATE POLICY "Allow all operations on user_locations" ON user_locations
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Sample query to test
-- SELECT * FROM user_locations;
