# Blipp Expo Frontend

The official Expo application for the Blipp platform, supporting web and mobile clients.

## Features
- **Keycloak OIDC Authentication**: Direct Access Grant login and session synchronization.
- **Microservices Verification**: Interactive live test against protected FastAPI microservices via Bearer JWT.
- **Production Web Container**: Multi-stage build producing an ultra-lightweight Nginx container with SPA routing.
- **Modern Dark Aesthetic**: Clean, responsive UI built with React Native Web components.

## Development Modes

### 1. Physical Mobile Device Testing (Expo Go via LAN)

To test the application on a physical iOS or Android device using Expo Go:

1. Ensure your physical phone and development workstation are connected to the **same Wi-Fi network**.
2. Make sure backend services are running in your cluster (`make all` or `kubectl get pods -n blipp`).
3. Run the automated mobile setup command from the repository root:
   ```bash
   make dev-mobile
   ```
   *This command automatically:*
   - Detects your workstation's local network IPv4 address (macOS and Linux compatible).
   - Generates `apps/blipp/.env` with `EXPO_PUBLIC_API_URL` and `EXPO_PUBLIC_KEYCLOAK_URL`.
   - Starts background `kubectl port-forward --address 0.0.0.0` for FastAPI (`8000`), Keycloak (`8080`), and MinIO (`9000`).
   - Launches Expo with `--host lan`.
   - Cleans up port-forwarding processes automatically when you press `Ctrl+C`.
4. Open the **Expo Go** app on your phone:
   - **Android**: Scan the QR code displayed in your terminal.
   - **iOS**: Scan the QR code using the default Camera app and tap the Expo Go prompt.

#### Manual Configuration
If you prefer to run Expo manually without `make dev-mobile`:
1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
2. Replace `localhost` with your workstation's LAN IP (e.g., `192.168.1.50`):
   ```env
   EXPO_PUBLIC_API_URL=http://192.168.1.50:8000/v1
   EXPO_PUBLIC_KEYCLOAK_URL=http://192.168.1.50:8080/keycloak
   ```
3. Expose backend services to your local network:
   ```bash
   kubectl port-forward --address 0.0.0.0 svc/auth-service 8000:8000 -n blipp &
   kubectl port-forward --address 0.0.0.0 svc/keycloak 8080:8080 -n blipp &
   kubectl port-forward --address 0.0.0.0 svc/minio 9000:9000 -n blipp &
   ```
4. Start the Expo server on LAN:
   ```bash
   npm run start:lan
   ```

#### Wi-Fi & Firewall Troubleshooting
- **Network Isolation**: Ensure your router does not enable "AP Isolation" or "Client Isolation", which prevents devices on Wi-Fi from reaching each other.
- **Firewall**: Ensure your workstation firewall (e.g. `ufw`, `pf`, or macOS Application Firewall) allows incoming TCP connections on ports `8000`, `8080`, `9000`, and `8081` (Metro bundler).
- **Expo Tunnel Fallback**: If your Wi-Fi network blocks peer-to-peer traffic, use Expo's cloud tunnel:
  ```bash
  npm run start:tunnel
  ```

### 2. Web Development

To test the web interface locally:
```bash
npm run web
```

## Build and Containerization
- **Dockerfile**: Two-stage build:
  1. `node:20-alpine` runs `npx expo export --platform web`.
  2. `nginx:1.27-alpine` serves production bundle on port 80.
- Subsequent builds are fast due to Docker layer caching on `package.json`.
