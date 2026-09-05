# Kubernetes Infrastructure Manifests

This directory contains declarative Kubernetes manifests for the Blipp microservices ecosystem, deployed onto `k3d` with Traefik Ingress.

## Namespace
All services operate within the isolated `blipp` namespace.

## Directory Structure
- `namespace.yaml`: Defines `blipp` namespace.
- `postgres/`: PostgreSQL 16 Stateful database deployment, PVC, and internal ClusterIP service.
- `keycloak/`:
  - `realm-configmap.yaml`: Pre-seeded realm configuration for `blipp` with `blipp-app` client and test user credentials.
  - `deployment.yaml`: Keycloak 26 Quarkus distribution with health probes and relative path `/keycloak`.
  - `service.yaml`: ClusterIP service on port 8080.
- `auth-service/`:
  - `deployment.yaml`: FastAPI container with non-root security context, resource limits, and health probes.
  - `service.yaml`: ClusterIP service on port 8000.
- `blipp-app/`:
  - `deployment.yaml`: High-performance Nginx container serving compiled Expo web SPA.
  - `service.yaml`: ClusterIP service on port 80.
- `ingress/`:
  - `ingressroute.yaml`: Traefik IngressRoute routing all host port 8419 requests to respective cluster services.
- `nats/`:
  - `deployment.yaml`: NATS 2.10 server with JetStream (`-js`) and persistent storage (`nats-pvc`).
  - `service.yaml`: ClusterIP service exposing client port 4222 and monitoring port 8222.
- `minio/`:
  - `deployment.yaml`: Standalone S3-compatible MinIO object storage with persistent volume (`minio-pvc`) and automated bucket directory creation.
  - `service.yaml`: ClusterIP service exposing S3 API on port 9000 and Web Console on port 9001.
  - `setup-job.yaml`: Post-deployment bucket provisioner ensuring `blipp-raw-uploads` and `blipp-audio-variants` exist with download policies.
