# Blipp Architecture Context

Blipp is an Expo/React Native audio-reels client backed by an event-driven microservice platform. Authentication is provided by Keycloak; there is no single-service authentication monolith or legacy JavaScript SPA in the active architecture.

## Active services

| Service | Responsibility |
| --- | --- |
| Keycloak (auth) | OIDC identity, token issuance, and JWKS |
| feed | Cursor-paginated reels and telemetry ingress |
| social_graph | Profiles, follows, and likes |
| messaging | Direct-message threads and messages |
| content_ingest | Multipart audio ingestion and content metadata |
| moderation | Reports and moderation decisions |
| analytics_worker | Consumes engagement events and aggregates listening analytics |
| transcode_worker | Consumes uploads and writes playable audio variants |

## Data and event flow

The client uploads multipart audio to Content Ingest, which streams the source to MinIO and emits `upload.received`. The Transcode Worker consumes that event, generates playback variants, stores them in MinIO, and publishes the resulting content state. Feed serves published items from PostgreSQL.

Engagement is batched by the client and sent to `POST /v1/events` on Feed. Feed publishes each validated event to NATS JetStream's `ENGAGEMENT` stream on subjects such as `engagement.play_progress`, `engagement.skip`, `engagement.play_complete`, `engagement.like`, `engagement.save`, and `engagement.follow`. The Analytics Worker consumes these durable events. Every engagement event includes a `session_id`.

PostgreSQL stores service data; Redis/Gorse may provide feed candidates, but published-content fallback remains available for cold starts. MinIO is the authoritative object store for upload inputs and transcodes.
