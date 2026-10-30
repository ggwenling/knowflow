-- Run once per KnowFlow database as a database administrator before Flyway.
-- This script creates login roles without passwords; inject credentials separately.
DO $roles$
DECLARE
    role_name text;
    role_is_unsafe boolean;
    role_can_login boolean;
    role_has_memberships boolean;
BEGIN
    FOREACH role_name IN ARRAY ARRAY[
        'knowflow_migrator',
        'knowflow_app',
        'knowflow_ai'
    ] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format(
                'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE '
                    'NOREPLICATION NOBYPASSRLS',
                role_name);
        END IF;

        SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls,
               rolcanlogin,
               EXISTS (
                   SELECT 1 FROM pg_auth_members
                    WHERE member = (SELECT oid FROM pg_roles WHERE rolname = role_name)
               )
          INTO role_is_unsafe, role_can_login, role_has_memberships
          FROM pg_roles
         WHERE rolname = role_name;

        IF role_is_unsafe OR NOT role_can_login OR role_has_memberships THEN
            RAISE EXCEPTION 'Role % must be a restricted LOGIN role', role_name;
        END IF;
    END LOOP;
END
$roles$;

CREATE SCHEMA IF NOT EXISTS knowflow AUTHORIZATION knowflow_migrator;
CREATE SCHEMA IF NOT EXISTS knowflow_flyway AUTHORIZATION knowflow_migrator;

DO $schemas$
DECLARE
    expected_owner oid := (SELECT oid FROM pg_roles WHERE rolname = 'knowflow_migrator');
BEGIN
    IF (SELECT nspowner FROM pg_namespace WHERE nspname = 'knowflow') <> expected_owner THEN
        RAISE EXCEPTION 'Schema knowflow must be owned by knowflow_migrator';
    END IF;
    IF (SELECT nspowner FROM pg_namespace WHERE nspname = 'knowflow_flyway') <> expected_owner THEN
        RAISE EXCEPTION 'Schema knowflow_flyway must be owned by knowflow_migrator';
    END IF;
END
$schemas$;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;

DO $vector_schema$
BEGIN
    IF (SELECT extnamespace FROM pg_extension WHERE extname = 'vector')
            <> 'public'::regnamespace THEN
        RAISE EXCEPTION 'The vector extension must be installed in schema public';
    END IF;
END
$vector_schema$;

GRANT USAGE ON SCHEMA public TO knowflow_app, knowflow_ai;
GRANT USAGE ON SCHEMA knowflow TO knowflow_app, knowflow_ai;
GRANT USAGE, CREATE ON SCHEMA knowflow, knowflow_flyway TO knowflow_migrator;

ALTER DEFAULT PRIVILEGES FOR ROLE knowflow_migrator IN SCHEMA knowflow
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO knowflow_app;
ALTER DEFAULT PRIVILEGES FOR ROLE knowflow_migrator IN SCHEMA knowflow
    GRANT USAGE, SELECT ON SEQUENCES TO knowflow_app;
