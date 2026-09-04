# Blipp Platform - Product Specifications

## Overview
Blipp is an enterprise cloud microservices foundation orchestrated by Kubernetes (k3d), Traefik Ingress, Keycloak OIDC, and FastAPI backend services, accessed via a modern web and mobile client.

## Target Audience & Tone
- **Audience**: Enterprise engineering teams, systems architects, and authenticated platform operators.
- **Tone**: Professional, precise, confident, utilitarian, state-of-the-art.
- **Visual Standard**: Linear / Stripe / Clerk design caliber. Zero AI slop (no generic purple neon glows, no nested card clutter, no low-contrast text).

## Core User Flows
1. **Authentication**:
   - Direct Access Grant authentication backed by Keycloak OIDC realm.
   - Clean, accessible sign-in with instant error feedback and session recovery.
   - User registration.
2. **Platform Management (Authenticated Dashboard)**:
   - Live session identity inspection (Subject ID, Roles, Verified Email, Token expiry).
   - End-to-end API execution panel testing secured FastAPI microservice endpoints with Bearer tokens.
   - Session lifecycle controls (Token refresh, Revocation/Sign out).
