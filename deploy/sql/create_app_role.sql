-- A database role for the API that cannot bypass Row Level Security (migration 0016 installs the policies; RLS_ENABLED=true uses them).
-- Neon's default owner role has BYPASSRLS, so policies only bite when the API connects as a role like this one.
-- Run once as the owner, then point DATABASE_URL at vitram_app and keep the owner's URL for migrations (AUTO_MIGRATE needs DDL rights).
CREATE ROLE vitram_app LOGIN PASSWORD 'CHANGE-ME' NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT USAGE ON SCHEMA public TO vitram_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO vitram_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vitram_app;
