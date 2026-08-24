ALTER TABLE recommendation_events
    ADD COLUMN event_id VARCHAR(64) NULL AFTER id,
    ADD COLUMN room_id VARCHAR(64) NULL AFTER event_id,
    ADD COLUMN rank_no INT NULL AFTER movie_id,
    ADD COLUMN model_version VARCHAR(64) NULL AFTER event_type,
    ADD COLUMN occurred_at TIMESTAMP NULL AFTER payload;

UPDATE recommendation_events
SET event_id = CONCAT('legacy-', id),
    occurred_at = COALESCE(occurred_at, created_at)
WHERE event_id IS NULL OR occurred_at IS NULL;

ALTER TABLE recommendation_events
    MODIFY event_id VARCHAR(64) NOT NULL,
    MODIFY room_id VARCHAR(64) NOT NULL,
    MODIFY occurred_at TIMESTAMP NOT NULL,
    ADD CONSTRAINT uq_recommendation_events_event_id UNIQUE (event_id),
    ADD INDEX idx_recommendation_events_round (round_id, occurred_at),
    ADD INDEX idx_recommendation_events_training (event_type, model_version, occurred_at);
