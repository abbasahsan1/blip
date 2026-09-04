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
  - `ingress.yaml`: Traefik Ingress routing all host port 8419 requests to respective cluster services.
