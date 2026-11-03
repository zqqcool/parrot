DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parrot_app') THEN
        CREATE ROLE parrot_app LOGIN PASSWORD 'test-only-app-password' NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'parrot_platform') THEN
        CREATE ROLE parrot_platform LOGIN PASSWORD 'test-only-platform-password' BYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE parrot_local TO parrot_app, parrot_platform;
GRANT USAGE ON SCHEMA public TO parrot_app, parrot_platform;

ALTER DEFAULT PRIVILEGES FOR ROLE parrot_local IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO parrot_app, parrot_platform;
ALTER DEFAULT PRIVILEGES FOR ROLE parrot_local IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO parrot_app, parrot_platform;
