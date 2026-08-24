ALTER TABLE unified_movies
    ADD COLUMN title_ko VARCHAR(255) NULL,
    ADD COLUMN title_en VARCHAR(255) NULL,
    ADD COLUMN overview_ko TEXT NULL,
    ADD COLUMN overview_en TEXT NULL,
    ADD COLUMN completeness_score INT NOT NULL DEFAULT 0,
    ADD COLUMN recommendation_eligible BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS movie_data_sources (
    movie_id VARCHAR(32) NOT NULL,
    source VARCHAR(16) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (movie_id, source),
    UNIQUE KEY uq_movie_source_id (source, source_id)
);
