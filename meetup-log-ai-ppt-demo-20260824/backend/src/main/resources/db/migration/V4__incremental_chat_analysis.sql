CREATE TABLE IF NOT EXISTS chat_analysis_progress (
    room_id VARCHAR(64) PRIMARY KEY,
    last_message_id BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE INDEX idx_chat_analysis_progress_message
    ON chat_analysis_progress(last_message_id);
