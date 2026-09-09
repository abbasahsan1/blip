-- Dedicated databases for microservices
SELECT 'CREATE DATABASE blipp_auth'    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='blipp_auth')\gexec
SELECT 'CREATE DATABASE blipp_ingest'  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='blipp_ingest')\gexec
SELECT 'CREATE DATABASE blipp_feed'    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='blipp_feed')\gexec
SELECT 'CREATE DATABASE blipp_social'  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='blipp_social')\gexec
SELECT 'CREATE DATABASE blipp_analytics' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='blipp_analytics')\gexec
SELECT 'CREATE DATABASE blipp_messaging' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='blipp_messaging')\gexec

-- Grant connection and administrative privileges to keycloak user
GRANT ALL PRIVILEGES ON DATABASE blipp_auth TO keycloak;
GRANT ALL PRIVILEGES ON DATABASE blipp_ingest TO keycloak;
GRANT ALL PRIVILEGES ON DATABASE blipp_feed TO keycloak;
GRANT ALL PRIVILEGES ON DATABASE blipp_social TO keycloak;
GRANT ALL PRIVILEGES ON DATABASE blipp_analytics TO keycloak;
GRANT ALL PRIVILEGES ON DATABASE blipp_messaging TO keycloak;
