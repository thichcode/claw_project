CREATE TABLE IF NOT EXISTS locations (
  id BIGSERIAL PRIMARY KEY,
  code VARCHAR(64) UNIQUE NOT NULL,
  name VARCHAR(128) NOT NULL,
  level VARCHAR(16) NOT NULL CHECK (level IN ('site','region','zone')),
  parent_id BIGINT REFERENCES locations(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS service_locations (
  service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  location_id BIGINT NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
  is_primary BOOLEAN DEFAULT FALSE,
  PRIMARY KEY(service_id, location_id)
);

ALTER TABLE services ADD COLUMN IF NOT EXISTS source_key VARCHAR(255);
ALTER TABLE alert_events ADD COLUMN IF NOT EXISTS location_id BIGINT REFERENCES locations(id) ON DELETE SET NULL;
ALTER TABLE incidents ADD COLUMN IF NOT EXISTS location_id BIGINT REFERENCES locations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_locations_level ON locations(level);
CREATE INDEX IF NOT EXISTS idx_alert_events_location_id ON alert_events(location_id);
CREATE INDEX IF NOT EXISTS idx_incidents_location_id ON incidents(location_id);
