# Blipp Authentication Service

FastAPI microservice providing OIDC session management and JWT authentication wired to Keycloak.

## Features
- **Keycloak OIDC Integration**: Verifies RS256 JWTs using Keycloak's cryptographic JWKS public certs.
- **Direct Access Grants**: Exposes clean JSON REST endpoints for mobile and web clients to login, register, refresh tokens, and logout.
- **Microservice Token Verification**: Protects backend endpoints via `Depends(get_current_user)`.
- **Docker Layer Caching**: Multi-stage, non-root container with dependency separation for fast builds.

## Endpoints

| Method | Endpoint | Description | Auth Required |
|---|---|---|---|
| `GET` | `/health` | Liveness / readiness probe & Keycloak status | No |
| `POST` | `/api/auth/login` | Login with username/password, returns tokens | No |
| `POST` | `/api/auth/register` | Register new user via Keycloak Admin API | No |
| `POST` | `/api/auth/refresh` | Refresh access token using refresh token | No |
| `POST` | `/api/auth/logout` | Revoke session in Keycloak | No |
| `GET` | `/api/auth/me` | Fetch user profile and roles from JWT | Yes (Bearer) |
| `GET` | `/api/protected/data` | Sample secured endpoint requiring valid token | Yes (Bearer) |

## Environment Variables
- `KEYCLOAK_URL`: Public Keycloak URL (e.g. `http://localhost:8419/keycloak`)
- `KEYCLOAK_INTERNAL_URL`: Internal cluster URL (e.g. `http://keycloak.blipp.svc.cluster.local:8080/keycloak`)
- `KEYCLOAK_REALM`: Keycloak realm name (`blipp`)
- `KEYCLOAK_CLIENT_ID`: Keycloak client ID (`blipp-app`)
- `KEYCLOAK_CLIENT_SECRET`: Keycloak client secret
- `KEYCLOAK_ADMIN` / `KEYCLOAK_ADMIN_PASSWORD`: Keycloak administrator credentials
