# Blipp — Repository Memory

Blipp is an audio-first Reels application. The production client is `apps/blipp`, an Expo Router TypeScript app using Zustand stores and a dark/orange interface. It is not the legacy JavaScript SPA described in older notes.

## Platform

The active platform is composed of eight services: Keycloak authentication, Feed, Social Graph, Messaging, Content Ingest, Moderation, Analytics Worker, and Transcode Worker.

Services authenticate requests by verifying Keycloak JWTs against JWKS. They communicate asynchronously through NATS JetStream. `UPLOADS` carries upload/transcode lifecycle events; `ENGAGEMENT` carries durable playback and social events. Analytics consumes the latter and requires a `session_id` on every event.

## Storage and request paths

MinIO stores original audio and derived playback variants. Content Ingest is the authoritative multipart upload entry point and emits `upload.received`; uploads do not use in-memory tracking or presigned bypass routes. The Transcode Worker processes those events. Feed retrieves published records from PostgreSQL and accepts client telemetry at `/v1/events`, publishing the events to JetStream.

Ingress routes each versioned endpoint to its owning service rather than a generic auth proxy. Keep API contracts versioned under `/v1`, use cursor pagination for feeds, and batch client telemetry rather than emitting a request for each progress tick.
