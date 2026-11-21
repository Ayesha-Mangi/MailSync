-- MailSync AI: run this whole file in the Supabase SQL Editor.
-- Configured for local embeddings (all-MiniLM-L6-v2); set EMBEDDING_PROVIDER=local in .env.

CREATE EXTENSION IF NOT EXISTS vector;

DO $$ BEGIN
    CREATE TYPE item_intent AS ENUM ('lost', 'found');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE item_status AS ENUM ('searching', 'matched', 'resolved');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id VARCHAR(255) UNIQUE NOT NULL,
    sender_email VARCHAR(255) NOT NULL,
    intent item_intent NOT NULL,
    item_name VARCHAR(150) NOT NULL,
    category VARCHAR(50) NOT NULL,
    color VARCHAR(50),
    brand VARCHAR(50),
    location VARCHAR(255) NOT NULL,
    event_date_time VARCHAR(100),
    summary TEXT NOT NULL,
    embedding vector(384),
    status item_status DEFAULT 'searching',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lost_item_id UUID REFERENCES items(id) ON DELETE CASCADE,
    found_item_id UUID REFERENCES items(id) ON DELETE CASCADE,
    similarity_score FLOAT NOT NULL,
    notified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (lost_item_id, found_item_id)
);

CREATE INDEX IF NOT EXISTS items_embedding_hnsw_idx
    ON items USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_items_status_intent ON items(status, intent);

-- Returns open items of the opposite intent, ranked by cosine similarity.
CREATE OR REPLACE FUNCTION match_items(
    query_embedding vector(384),
    match_intent item_intent,
    match_threshold FLOAT,
    max_results INT
)
RETURNS TABLE (
    id UUID,
    item_name VARCHAR,
    category VARCHAR,
    color VARCHAR,
    location VARCHAR,
    summary TEXT,
    sender_email VARCHAR,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        items.id,
        items.item_name,
        items.category,
        items.color,
        items.location,
        items.summary,
        items.sender_email,
        (1 - (items.embedding <=> query_embedding))::FLOAT AS similarity
    FROM items
    WHERE items.status = 'searching'
      AND items.intent = match_intent
      AND items.embedding IS NOT NULL
      AND (1 - (items.embedding <=> query_embedding)) >= match_threshold
    ORDER BY items.embedding <=> query_embedding ASC
    LIMIT max_results;
END;
$$;
