# Secret Management

## Current State

> **WARNING**: Real credentials are currently stored in `k8s/secrets.yaml`.
> This is acceptable ONLY for a local isolated dev cluster.
> This file MUST NOT be used in staging or production.

Credentials committed to the repo (local dev only):
- MinIO: `minioadmin` / `minioadmin`
- PostgreSQL: `keycloak` / `keycloak_secure_db_pass`
- Keycloak admin: `admin` / `admin_master_password`
- Keycloak client secret: `blipp-secret-client-token`
- Gorse API key: auto-generated at repo init time

## Intended Production Architecture (T14)

Secrets should be managed via External Secrets Operator:

1. Store real secrets in a secret backend (e.g. HashiCorp Vault, AWS Secrets Manager)
2. Deploy External Secrets Operator to the cluster
3. Create ExternalSecret resources that sync from the secret backend into k8s Secret objects
4. Remove k8s/secrets.yaml (or replace with an ExternalSecret manifest)
5. Rotate all credentials that have ever been committed to this repository

### Action Required Before Any Public/Production Deployment
- [ ] Choose a secret backend provider
- [ ] Rotate ALL credentials listed above
- [ ] Remove k8s/secrets.yaml from Git history (git filter-repo or BFG Repo Cleaner)
- [ ] Implement External Secrets Operator manifests
- [ ] Enforce pre-commit hook to block credential commits (git-secrets or detect-secrets)

## Per-Service Credentials (T13 - Deferred)

Currently all services share one Postgres user (keycloak). Per-service DB credentials
are tracked in T13 and will be implemented in a follow-up pass:
- content_db_user -> blipp_ingest only
- feed_db_user -> blipp_feed only
- social_db_user -> blipp_social only
- analytics_db_user -> blipp_analytics only
- messaging_db_user -> blipp_messaging only
- moderation_db_user -> blipp_moderation only
- gorse_db_user -> blipp_gorse only
