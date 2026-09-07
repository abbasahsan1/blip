# Stage 1: Build static web bundle
FROM node:20-alpine AS builder

WORKDIR /app

# Cache npm dependencies
COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

# Copy application source
COPY . .

# Export web bundle — Expo Router outputs to /app/dist
ENV NODE_ENV=production
RUN npx expo export --platform web

# Stage 2: Production Nginx
FROM nginx:1.27-alpine

# Security: run as non-root
RUN addgroup -S blipp && adduser -S blipp -G blipp

# Copy compiled static assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

RUN chown -R blipp:blipp /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
