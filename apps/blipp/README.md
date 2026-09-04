# Blipp Expo Frontend

The official Expo application for the Blipp platform, supporting web and mobile clients.

## Features
- **Keycloak OIDC Authentication**: Direct Access Grant login and session synchronization.
- **Microservices Verification**: Interactive live test against protected FastAPI microservices via Bearer JWT.
- **Production Web Container**: Multi-stage build producing an ultra-lightweight Nginx container with SPA routing.
- **Modern Dark Aesthetic**: Clean, responsive UI built with React Native Web components.

## Build and Containerization
- **Dockerfile**: Two-stage build:
  1. `node:20-alpine` runs `npx expo export --platform web`.
  2. `nginx:1.27-alpine` serves production bundle on port 80.
- Subsequent builds are fast due to Docker layer caching on `package.json`.
