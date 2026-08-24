ALTER TABLE chat_rooms
    ADD COLUMN state_version BIGINT NOT NULL DEFAULT 0;

ALTER TABLE chat_messages
    ADD COLUMN idempotency_key VARCHAR(128) NULL,
    ADD CONSTRAINT uq_chat_message_idempotency UNIQUE (room_id, idempotency_key);
