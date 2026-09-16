# Blipp Implementation Audit

## 1. Executive Summary
This audit outlines critical architectural violations, incomplete features, and UI/HCI problems in the Blipp repository. While the repository claims to implement a scalable microservices architecture with a React Native frontend, the reality is a monolithic database schema disguised as microservices, complete with hardcoded credentials, fake AI integration, and broken event flows. 

## 2. Current Architecture
The backend is split into several Python microservices (`auth`, `content_ingest`, `feed`, `messaging`, `moderation`, `social_graph`, `analytics_worker`, `transcode_worker`). The frontend is a React Native Expo application under `apps/blipp`. Communication occurs via HTTP REST endpoints and NATS JetStream events.

## 3. Actual Service Ownership
Service ownership is completely compromised. Services do not own their databases; instead, a single shared `database.py` in `libs/common/blipp_common` defines all tables and connections. Cross-service foreign keys are actively used (e.g., `uploads` and `blipps` referencing `users_profile`). 

## 4. Actual Data Flow
- **Service reading another service's database**: The `feed` service queries the `blipps` and `users_profile` tables directly to hydrate its feed, bypassing `content_ingest` and `social_graph` APIs.
- **Events emitted after direct DB writes**: `content_ingest` upserts into the database, commits the transaction, and *then* emits events like `engagement.blipp.published`. If the application crashes between these two steps, the event is permanently lost.

## 5. Critical Broken Flows
- **Fake event flows / Mocked workers**: The `transcode_worker` unconditionally publishes a fake `copyright.cleared` event. There is no real copyright worker.
- **Recommendation ranking being discarded**: The `feed` service queries the Gorse recommendation engine for candidates, but when hydrating these from PostgreSQL, it forces a strict `ORDER BY b.created_at DESC, b.blipp_id DESC`, entirely discarding the algorithmic ranking and turning it into a simple chronological feed.

## 6. API Mismatches
- **Components doing network requests themselves**: The React Native `AudioReel` component directly calls `api.post('/v1/reports', ...)` instead of utilizing a structured store.

## 7. Authentication Issues
- **Hardcoded credentials**: The moderation service hardcodes `admin_master_password` to authenticate with the Keycloak Admin API when suspending a user in `services/moderation/app/event_handlers.py`.

## 8. Feed Issues
- **Fake URLs / Demo advertisements**: The feed service interleaves ads server-side using a hardcoded fake URL (`https://cdn.blipps.internal/ads/sample-ad.aac`).

## 9. Upload Issues
Upload flow generally works, but processing status relies on the transcode worker completing successfully.

## 10. Audio Issues
- **Hardcoded media duration**: The frontend hardcodes a fallback duration of `30` seconds in `AudioReel` and `api.ts`, which breaks scrubbing for audio items missing duration metadata.

## 11. Engagement Issues
- **Optimistic state that doesn't rollback correctly**: The `toggleLike` function in `feedStore.ts` optimistically increments likes and assumes `isLiked: false` on error, ignoring the actual previous state.

## 12. Messaging Issues
Messaging DM flow exists, but is not fully integrated with real-time sockets; shares are sent via HTTP calls.

## 13. Event Issues
- Database transactions and NATS event emissions are decoupled without an outbox pattern.

## 14. Mock/Placeholder Implementations
- **Fake copyright results**: As mentioned, `transcode_worker` bridges copyright clearance without real scanning.
- **Mocked workers**: Reporting intake exists in `moderation`, but no worker actually actions the reports. 

## 15. UI/HCI Problems
- **Excessive shadows/glows**: The `centerPlayBadge` uses a large shadow radius (12) which looks out of place.
- **Unnecessary animations / Animation loops**: The audio track tag text uses an infinite `Animated.loop`, causing constant CPU usage even when the user isn't interacting.
- **Pill controls**: Inconsistent use of sleek pill follow buttons vs frosted action buttons.

## 16. Animation/Performance Problems
- Infinite animation loops in the feed card track.

## 17. Infrastructure Gaps
- Minimal KEDA scaling configs; most deployments are basic.

## 18. Testing Gaps
- There are only 4 test files across the entire microservice architecture. 

## 19. Prioritized Repair Order
1. Fix shared database and cross-service queries to isolate data models.
2. Implement transaction outbox for events to prevent data loss.
3. Fix the feed algorithmic sorting to respect Gorse rankings.
4. Remove hardcoded credentials.
5. Fix frontend optimistic rollback.

---

### CRITICAL ROOT CAUSES
1. `libs/common/blipp_common/database.py` defines all tables in one monolithic file, destroying microservice data isolation.
2. NATS event emissions are not atomically tied to database transactions.
3. The `feed` service forces `ORDER BY created_at DESC` overriding the Gorse recommendation system IDs.
4. Hardcoded admin passwords and fake CDN URLs in core application flows.

### DO NOT FIX YET
1. Shared database schema violations.
2. Recommendation ranking destruction in feed.
3. Fake copyright event injection.
4. UI component animation loops.
5. Frontend optimistic state rollback bug.
