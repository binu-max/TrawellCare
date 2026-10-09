DO $$
BEGIN
    CREATE ROLE integration_user LOGIN PASSWORD 'integration';
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

GRANT ALL PRIVILEGES ON DATABASE trawellcare TO integration_user;

CREATE SCHEMA IF NOT EXISTS integration AUTHORIZATION integration_user;
GRANT ALL ON SCHEMA integration TO integration_user;

DO $$
BEGIN
    CREATE ROLE platform_user LOGIN PASSWORD 'platform';
EXCEPTION
    WHEN duplicate_object THEN NULL;
END
$$;

CREATE SCHEMA IF NOT EXISTS platform AUTHORIZATION platform_user;
GRANT ALL ON SCHEMA platform TO platform_user;
GRANT ALL PRIVILEGES ON DATABASE trawellcare TO platform_user;

CREATE DATABASE trawellcare_test OWNER integration_user;
