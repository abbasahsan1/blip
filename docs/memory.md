# Blipp — AI Agent Memory & Master Context

> File: `memory.md`
> Last updated: 2026-09-05
> Workspace: `/home/ali/blipp-dev`
> Host IP: `100.122.207.32` | Host port: `8419`
> Cluster: `k3d` cluster named `blipp-cluster`, namespace `blipp`

---

## 1. Product Description

**Blipp** is an audio-only short-form content feed — TikTok/Reels-style but for audio clips sourced from podcasts, interviews, documentaries, and spoken content.

**Core use case:** Background-screen consumption (driving, cycling, commuting) without the data cost of video.

The original no-code prototype lives at: https://github.com/abbasahsan1/blipp (React Native + Expo Router + TypeScript, dark-only, audio-first).

Production development started in this repo, building each feature properly one at a time.

---

## 2. Repository Layout

```
/home/ali/blipp-dev/
├── apps/
│   └── blipp/                          ← Expo React Native Web frontend (TypeScript Expo Router)
│       ├── app/
│       │   ├── _layout.tsx             ← Root layout, font loading, session bootstrap
│       │   ├── +not-found.tsx          ← 404 fallback screen
│       │   ├── auth/
│       │   │   ├── _layout.tsx
│       │   │   ├── sign-in.tsx         ← Sign-in (email/password + Google OAuth)
│       │   │   └── sign-up.tsx         ← Sign-up form
│       │   └── (tabs)/
│       │       ├── _layout.tsx         ← Bottom tab navigator (Reels, Upload, Profile)
│       │       ├── index.tsx           ← Audio reels feed (FlatList scroll-snap, Trending/New)
│       │       ├── profile.tsx         ← User profile & session controls
│       │       └── upload.tsx          ← Audio clip upload form
│       ├── components/
│       │   ├── audio/
│       │   │   └── AudioReel.tsx       ← Per-item reel card with waveform, scrubber, controls
│       │   └── auth/
│       │       └── GoogleSignInButton.tsx ← Google OAuth button
│       ├── lib/
│       │   ├── api.ts                  ← HTTP client (uses window.location.origin)
│       │   ├── palette.ts              ← Dark design system tokens
│       │   ├── types.ts                ← TypeScript models (User, AudioPost, etc.)
│       │   └── store/
│       │       ├── feedStore.ts        ← Audio feed Zustand store
│       │       └── sessionStore.ts     ← Keycloak OIDC session Zustand store
│       ├── app.config.ts               ← Expo config (output: single, viewport: mobile)
│       ├── nginx.conf                  ← Production Nginx serving compiled Expo SPA
│       ├── Dockerfile                  ← 2-stage: node builder → nginx:1.27-alpine
│       └── package.json
├── services/
│   └── auth/                           ← FastAPI authentication microservice
│       ├── app/
│       │   ├── main.py                 ← FastAPI app (docs: /api/docs)
│       │   ├── core/
│       │   │   ├── config.py           ← Pydantic settings
│       │   │   └── security.py         ← JWT verification (RS256 + JWKS cache)
│       │   ├── api/v1/
│       │   │   ├── auth.py             ← /api/auth/* endpoints
│       │   │   └── protected.py        ← /api/protected/* endpoints
│       │   └── models/schemas.py
│       ├── requirements.txt
│       └── Dockerfile                  ← python:3.12-slim
├── k8s/
│   ├── namespace.yaml
│   ├── keycloak/
│   │   ├── deployment.yaml             ← Keycloak 26.1.3 (KC_HOSTNAME=/keycloak)
│   │   ├── service.yaml
│   │   └── realm-configmap.yaml        ← blipp realm pre-seeded
│   ├── postgres/                       ← PostgreSQL 16 backing Keycloak
│   ├── auth-service/                   ← Deployment + Service for FastAPI
│   ├── blipp-app/                      ← Deployment + Service for Expo frontend
│   └── ingress/
│       └── ingress.yaml                ← Traefik routes (see below)
├── docs/                               ← Documentation & Architecture
│   ├── memory.md                       ← THIS FILE — master memory for AI agents
│   ├── context.md                      ← Legacy context file
│   ├── DESIGN.md                       ← Design principles & palette
│   └── PRODUCT.md                      ← Product scope & specification
├── Makefile                            ← make all / make destroy
├── .env.example                        ← Template environment config
└── README.md
```

---

## 3. Live Cluster State

| Component | Image | Internal DNS |
|---|---|---|
| PostgreSQL 16 | postgres:16-alpine | postgres.blipp.svc.cluster.local:5432 |
| Keycloak 26.1.3 | quay.io/keycloak/keycloak:26.1.3 | keycloak.blipp.svc.cluster.local:8080 |
| FastAPI auth-service | blipp-auth-service:latest | auth-service.blipp.svc.cluster.local:8000 |
| Expo blipp-app (Nginx) | blipp-app:latest | blipp-app.blipp.svc.cluster.local:80 |

---

## 4. Traefik Ingress Routes

All traffic enters on host port `8419`.

| Public Path | Internal Service | Notes |
|---|---|---|
| `/` | `blipp-app:80` | Expo SPA (SPA fallback via nginx try_files) |
| `/keycloak` | `keycloak:8080` | Keycloak admin + OIDC |
| `/v1/auth` | `auth-service:8000` | Versioned FastAPI auth microservice |
| `/api` | `auth-service:8000` | FastAPI auth microservice |
| `/api/docs` | `auth-service:8000` | Swagger UI |
| `/health` | `auth-service:8000` | Liveness probe |

---

## 5. Live Endpoints

- Blipp Web App: http://100.122.207.32:8419/
- Keycloak Admin Console: http://100.122.207.32:8419/keycloak
- FastAPI Swagger UI: http://100.122.207.32:8419/api/docs
- Keycloak OIDC Discovery: http://100.122.207.32:8419/keycloak/realms/blipp/.well-known/openid-configuration
- Keycloak Token Endpoint: http://100.122.207.32:8419/keycloak/realms/blipp/protocol/openid-connect/token
- Versioned Auth Route: http://100.122.207.32:8419/v1/auth/login

---

## 6. FastAPI Auth Service API Contract

Base paths: `/v1/auth` and `/api/auth`

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/auth/login` (or `/api/auth/login`) | None | Email/password → access+refresh tokens |
| POST | `/v1/auth/register` (or `/api/auth/register`) | None | Creates user in Keycloak realm |
| POST | `/v1/auth/refresh` (or `/api/auth/refresh`) | None | Refresh token → new access token |
| POST | `/v1/auth/logout` (or `/api/auth/logout`) | None | Revokes Keycloak session |
| GET | `/v1/auth/me` (or `/api/auth/me`) | Bearer | Returns user profile from JWT |
| GET | `/api/protected/data` | Bearer | Sample protected resource |
| GET | `/api/health` / `/health` | None | Health + Keycloak connectivity probe |

### Error Envelope Contract (All 4xx/5xx Responses)
```json
{
  "error": {
    "code": "string",
    "message": "string",
    "request_id": "uuid"
  }
}
```
All HTTP responses include header: `X-Request-ID: <uuid>`.


Token validation: RS256, JWKS from keycloak service internally, 10-min cache. Issuer must end with `/realms/blipp`.

---

## 7. Keycloak Configuration

- Version: 26.1.3 Quarkus
- KC_HTTP_RELATIVE_PATH=/keycloak
- KC_HOSTNAME=http://100.122.207.32:8419/keycloak
- KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true
- KC_PROXY_HEADERS=xforwarded
- Realm: `blipp` (pre-seeded via configmap)
- Client: `blipp-app` (public, Direct Access Grants enabled)
- Test user: `testuser` / `TestPassword123!`
- Admin: `admin` / `admin_master_password`
- Google OAuth: NOT YET CONFIGURED (pending credentials from user)

---

## 8. Frontend Architecture

Built using React Native + Expo Router TypeScript:
- **Routing**: File-based under `apps/blipp/app`
- **Audio Reel Card**: `components/audio/AudioReel.tsx`
- **State**: Zustand stores (`lib/store/sessionStore.ts`, `lib/store/feedStore.ts`)
- **API Client**: `lib/api.ts` (proxied through Traefik)
- **Styling**: Pure dark design system in `lib/palette.ts`

---

## 9. Design System

Color Palette (dark-only):
- background: `#09090b`
- surface: `#121215`
- card: `#18181b`
- border: `#27272a`
- text: `#fafafa`
- textSecondary: `#a1a1aa`
- textMuted: `#71717a`
- primary: `#ffffff` (buttons)
- accent: `#2563eb` (blue highlights)
- success: `#10b981`
- error: `#ef4444`

Rules:
- No backend jargon on any user-facing screen
- All touch targets ≥ 44px
- Responsive layouts (`useWindowDimensions`)
- Dark-only, modern sans-serif typography

---

## 10. Infrastructure & Development Workflow

Makefile targets: `make all`, `make destroy`, `make build`, `make import`, `make deploy`, `make status`, `make logs`.

**IMPORTANT**: Use `DOCKER_BUILDKIT=0` — the host Docker does not have buildx.

Rebuild commands:
```bash
# Auth service
docker build -t blipp-auth-service:latest services/auth
k3d image import blipp-auth-service:latest -c blipp-cluster
kubectl rollout restart deployment auth-service -n blipp

# Frontend
cd /home/ali/blipp-dev && DOCKER_BUILDKIT=0 docker build -t blipp-app:latest apps/blipp
k3d image import blipp-app:latest -c blipp-cluster
kubectl rollout restart deployment blipp-app -n blipp
```

---

## 11. Master Development Plan

### Phase 1 — Auth Foundation (IN PROGRESS)
- [x] Keycloak 26 OIDC running in k3d
- [x] FastAPI auth service with RS256 JWT validation
- [x] Migrate frontend to full TypeScript Expo Router app (AudioReels feed, tabs, auth)
- [x] Wire Keycloak to frontend (sessionStore with JWT + refresh token handling via FastAPI)
- [x] /api/docs accessible via Traefik
- [x] /keycloak routes to Admin UI correctly
- [ ] Add Google OAuth (configure Keycloak Identity Provider + frontend button — pending credentials)

### Phase 2 — Core Feed
- [ ] Audio post data model + PostgreSQL schema
- [ ] Feed API endpoint (`GET /api/feed`)
- [ ] AudioReel component full audio playback integration (`expo-av` / HTML5 Audio)
- [ ] Auto-play on scroll into view
- [ ] Playback controls (play/pause, scrubber, speed 1x/1.5x/2x)
- [ ] Background audio (works with screen off on mobile)

### Phase 3 — Content
- [ ] Audio upload endpoint (`POST /api/posts`)
- [ ] Upload screen with audio picker + metadata form

### Phase 4 — Social
- [ ] Like/unlike, follow/following, user profiles

### Phase 5 — Discovery
- [ ] Search, category filtering, personalization

---

## 12. Open Items / Blockers

1. **Google OAuth Credentials needed from user**:
   - Google Cloud Console → APIs & Services → OAuth 2.0 Client ID (Web application type)
   - Authorized redirect URI: `http://100.122.207.32:8419/keycloak/realms/blipp/broker/google/endpoint`
   - Needed values: `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`

---

## 13. How to Resume Work (New Chat / Next Agent)

1. **Read `memory.md` first** to understand the architecture, live state, and conventions.
2. Check live cluster: `kubectl get pods -n blipp`
3. See Phase checklist (Section 11) to pick up the next task.
4. Never hardcode `localhost` — always use `100.122.207.32`.
5. No port forwarding — all traffic routes through Traefik on port `8419`.
6. Run `DOCKER_BUILDKIT=0 docker build` (do not use docker buildx).

Quick health check:
```bash
curl -s -I http://100.122.207.32:8419/
curl -s -I http://100.122.207.32:8419/api/docs
curl -s http://100.122.207.32:8419/api/health | jq .
kubectl get pods -n blipp
```
