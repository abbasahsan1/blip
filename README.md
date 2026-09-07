# Blipp Microservices Platform

A production-grade microservices foundation running locally inside a **k3d** Kubernetes cluster. Ingress routing is orchestrated by **Traefik** on host port `8419` without any port-forwarding.

## Architecture

```
                    Host Client (Browser / Mobile)
                               │
                               ▼
                    http://localhost:8419
                               │
                  ┌────────────┴────────────┐
                  │   k3d Load Balancer     │
                  │   Traefik Ingress       │
                  └────────────┬────────────┘
                               │
       ┌───────────────────────┼───────────────────────┐
       │ Path: /               │ Path: /keycloak       │ Path: /api
       ▼                       ▼                       ▼
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│  blipp-app   │       │   keycloak   │       │ auth-service │
│  Expo SPA    │       │  OIDC Server │       │   FastAPI    │
│  Port 80     │       │  Port 8080   │       │  Port 8000   │
└──────────────┘       └───────┬──────┘       └───────┬──────┘
                               │                      │
                               │ (JDBC)               │ (JWKS / Verify)
                               ▼                      │
                       ┌──────────────┐               │
                       │   postgres   │◄──────────────┘
                       │  Database    │
                       │  Port 5432   │
                       └──────────────┘
```

All microservices run inside the isolated `blipp` Kubernetes namespace with `ClusterIP` services.

## Prerequisites
- **Docker**: Engine 20.10+
- **k3d**: v5.0+
- **kubectl**: v1.28+
- **make**: standard GNU make

## Quick Start

### 1. Launch Platform
To build all containers, launch the k3d cluster, import images, and deploy all services:

```bash
make all
```

Once deployment completes, the following endpoints are live:
- **Expo Web Application**: [http://100.122.207.32:8419/](http://100.122.207.32:8419/) (or `http://localhost:8419/`)
- **Keycloak Administration & IAM**: [http://100.122.207.32:8419/keycloak](http://100.122.207.32:8419/keycloak)
- **FastAPI Interactive Swagger UI**: [http://100.122.207.32:8419/api/docs](http://100.122.207.32:8419/api/docs)
- **FastAPI Auth Service Health**: [http://100.122.207.32:8419/api/health](http://100.122.207.32:8419/api/health)
- **Keycloak OIDC Discovery**: [http://100.122.207.32:8419/keycloak/realms/blipp/.well-known/openid-configuration](http://100.122.207.32:8419/keycloak/realms/blipp/.well-known/openid-configuration)

### 2. Default Test Credentials
The `blipp` realm is pre-seeded with:
- **Username**: `testuser`
- **Password**: `TestPassword123!`
- **Role**: `user`

Keycloak Master Admin:
- **Username**: `admin`
- **Password**: `admin_master_password` (defined in `.env`)

### 3. Teardown
To cleanly destroy the cluster and release all allocated resources:

```bash
make destroy
```

---

## End-to-End (E2E) Testing with Playwright

End-to-end tests are executed using **Playwright (TypeScript)** against the Expo Web application and microservices backend.

### Running Tests
Execute tests headlessly in Chromium:
```bash
make test-e2e
# or directly:
npx playwright test
```

Launch the interactive Playwright UI mode for live debugging:
```bash
make test-e2e-ui
# or directly:
npx playwright test --ui
```

### Test Suite Coverage (`e2e/tests/`):
- **Authentication (`auth.spec.ts`)**: User login, credential validation, session initialization, and operator profile parameters.
- **Upload Pipeline & Playback (`upload-and-playback.spec.ts`)**: Authenticated multipart audio upload, progressive upload progress (0% -> 100%), live transcoding polling transitions, and feed item display with audio player initialization.

---

## Service Overview

### 1. `apps/blipp` (Expo Frontend)
- **Tech Stack**: React Native Web / Expo 51+ served via Nginx 1.27 Alpine.
- **Port**: Exposed internally on port `80`, routed from `http://localhost:8419/`.
- **Features**:
  - Direct Access Grant authentication via Keycloak.
  - Interactive test calling secured FastAPI endpoint (`/api/protected/data`) using Bearer JWT.
  - Token refresh and session management.
  - User registration.

### 2. `services/auth` (FastAPI Microservice)
- **Tech Stack**: Python 3.12, FastAPI, Uvicorn, Python-Jose.
- **Port**: Exposed internally on port `8000`, routed from `http://localhost:8419/api`.
- **Endpoints**:
  - `POST /api/auth/login`: Direct login returning access and refresh tokens.
  - `POST /api/auth/register`: Creates user in Keycloak realm.
  - `POST /api/auth/refresh`: Exchanges refresh token for new access token.
  - `POST /api/auth/logout`: Revokes user session.
  - `GET /api/auth/me`: Authenticated profile endpoint requiring valid Keycloak JWT.
  - `GET /api/protected/data`: Sample microservice resource protected by Bearer token.
  - `GET /health` / `GET /api/health`: Readiness probe.

### 3. Keycloak & PostgreSQL
- **Keycloak 26.x Quarkus**: Relative path `/keycloak`, OIDC realm `blipp`, client `blipp-app` (public PKCE) and `blipp-auth-service`.
- **PostgreSQL 16 Alpine**: Backing store for Keycloak with persistent volume storage.

---

## Adding New Services to the Base

To add a new microservice (e.g. `services/order-service`):
1. Create directory `services/order-service` with its `Dockerfile`.
2. Add build and import commands to the `Makefile`:
   ```makefile
   IMAGE_ORDER ?= blipp-order-service:latest
   build:
       docker build -t $(IMAGE_ORDER) ./services/order-service
   import:
       k3d image import $(IMAGE_ORDER) -c $(CLUSTER_NAME)
   ```
3. Add Kubernetes manifests under `k8s/order-service/` (Deployment + Service).
4. Expose the route in `k8s/ingress/ingress.yaml` under `rules.http.paths`:
   ```yaml
   - path: /api/orders
     pathType: Prefix
     backend:
       service:
         name: order-service
         port:
           number: 8080
   ```
5. Deploy using `make deploy`.

---

## Documentation

Detailed architectural and design documentation is maintained in the [`docs/`](./docs) directory:
- [`docs/memory.md`](./docs/memory.md): Master context & system state for AI agents
- [`docs/DESIGN.md`](./docs/DESIGN.md): Design system, palette tokens, and UI guidelines
- [`docs/PRODUCT.md`](./docs/PRODUCT.md): Product vision, specifications, and user stories
- [`docs/context.md`](./docs/context.md): Codebase history and reference mappings

