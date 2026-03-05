CREATE TABLE IF NOT EXISTS service_dependencies (
  id BIGSERIAL PRIMARY KEY,
  from_service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  to_service_id INT NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  dependency_type VARCHAR(50) NOT NULL DEFAULT 'runtime_call',
  criticality VARCHAR(20) NOT NULL DEFAULT 'medium',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT uq_service_dependencies UNIQUE (from_service_id, to_service_id)
);

CREATE TABLE IF NOT EXISTS incident_hypotheses (
  id BIGSERIAL PRIMARY KEY,
  incident_id BIGINT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  hypothesis TEXT NOT NULL,
  confidence NUMERIC(4,3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  rank INT NOT NULL,
  evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS incident_timeline (
  id BIGSERIAL PRIMARY KEY,
  incident_id BIGINT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  event_time TIMESTAMPTZ NOT NULL,
  event_type VARCHAR(50) NOT NULL,
  title VARCHAR(255) NOT NULL,
  details JSONB NOT NULL DEFAULT '{}'::jsonb,
  source VARCHAR(50),
  actor_id INT REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_service_deps_from ON service_dependencies(from_service_id);
CREATE INDEX IF NOT EXISTS idx_service_deps_to ON service_dependencies(to_service_id);
CREATE INDEX IF NOT EXISTS idx_hypothesis_incident_rank ON incident_hypotheses(incident_id, rank);
CREATE INDEX IF NOT EXISTS idx_timeline_incident_time ON incident_timeline(incident_id, event_time ASC);
