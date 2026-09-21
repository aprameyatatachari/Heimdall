-- Creates the dedicated database used by integration tests.
-- Executed once, on first initialization of the PostgreSQL data volume.
SELECT 'CREATE DATABASE heimdall_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'heimdall_test')\gexec
