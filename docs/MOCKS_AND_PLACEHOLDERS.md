# Mocks and Placeholders Audit

This document classifies occurrences of technical debt keywords (`TODO`, `FIXME`, `mock`, `placeholder`, `fake`, etc.) across the repository. 

## Classification Rules
- **TEST**: Test-only mocks or fixtures. Should be kept.
- **DEV_ONLY**: Mocks intended for local development.
- **REAL**: Real implementations that incidentally use keywords (e.g., standard library usage).
- **REMOVE**: Fake production implementations pretending to be real.

## Occurrences

### 1. Test Fixtures (Keep)
- `services/social_graph/tests/test_social_graph.py`: Contains `MockDatabasePool`, `MockConnection`, `mock_user_alice`, `mock_user_bob`. Status: **TEST**.
- `services/messaging/tests/test_messaging.py`: Contains `mock_pool()`. Status: **TEST**.
- `services/feed/tests/test_events.py`: Mock DB connections and consumers. Status: **TEST**.
- `services/moderation/tests/test_event_handlers.py`: Mocks for event handlers. Status: **TEST**.

### 2. Real Implementations (Keep)
- `services/transcode_worker/app/main.py`: Uses `tempfile.TemporaryDirectory`. This is a standard library function and not a placeholder. Status: **REAL**.
- `apps/blipp/lib/audio/listenTracker.ts`: Contains the comment `// Strictly require authenticated user; do not emit telemetry with dummy fallback UUIDs`. This enforces correct behavior. Status: **REAL**.
- `services/auth/app/api/v1/auth.py`: Sets `"temporary": False` in Keycloak credentials payload. This is a real domain concept. Status: **REAL**.
- `apps/blipp/app/...`: Uses React Native `placeholder` properties (e.g., `placeholder="Search @username..."`). These are real UI elements. Status: **REAL**.
- `apps/blipp/package-lock.json`: Dependency hash contains `demo`. Status: **REAL**.

### 3. Fake Implementations / Placeholders (Remove or Refactor)
- **Advertisements (`services/feed/app/api/v1/feed.py`)**: Interleaves a fake `ad-{uuid}` every 5 items with `audio_url="https://cdn.blipps.internal/ads/sample-ad.aac"`. Status: **REMOVE**. (No real ad backend exists, so it must not fake it).
- **Copyright Scanning (`services/content_ingest/app/event_handlers.py`)**: Publishes `copyright.scan.requested` but there is no actual consumer to perform the scan and emit `copyright.cleared`. Instead of pretending it cleared, the system simply bypasses it if `FEATURE_COPYRIGHT_SCAN_ENABLED` is false. Status: **REMOVE / IMPLEMENT INTERFACE**. If the feature is enabled, there is no service to handle it.
- **Out of Band Sessions (`services/social_graph/app/api/v1/likes.py`)**: Uses `session_id: str(uuid.uuid4())` with comment `dummy session for out of band`. Status: **DEV_ONLY / REMOVE**.

## Audit of Specific Domains
- **Copyright**: Currently no real copyright scanner exists. If `FEATURE_COPYRIGHT_SCAN_ENABLED` is true, Blipps hang in `processing` state because no service emits `copyright.cleared`.
- **Advertisements**: Fake ads are hardcoded into the feed pagination logic. This violates the rule "A fake production implementation must not report success."
- **AI Processing / Recommendations**: The recommendation system uses an actual Gorse instance (`GET /api/recommend/{user_id}`). Status: Real.
- **Verification**: `verification_status` is passed from Keycloak/DB correctly. Status: Real.
- **Moderation**: `services/moderation/` has a real Takdown & Strike workflow (`reports/{id}/action`). Status: Real.
- **Media URLs / Transcoding**: Real MinIO logic exists in `transcode_worker`. Status: Real.
- **Duration**: Extracted by `ffmpeg` in `transcode_worker`. Status: Real.
- **Authentication**: Keycloak used for JWT verification. Status: Real.
- **Credentials**: Keycloak `admin-cli` used for account suspension. Status: Real.

## Action Plan
1. Edit `services/feed/app/api/v1/feed.py` to completely remove Stage 5 Server-side ad interleaving.
2. Edit `services/social_graph/app/api/v1/likes.py` and other services to resolve the dummy session UUIDs.
3. Review `services/content_ingest/app/event_handlers.py` and `services/moderation/app/event_handlers.py` to add explicit Interface, Production, and Test implementations for Copyright scanning.
