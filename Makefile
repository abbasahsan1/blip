SHELL := /bin/bash

# Configuration & Environment Variables
ENV_FILE ?= .env
ifneq (,$(wildcard $(ENV_FILE)))
    include $(ENV_FILE)
    export
endif

CLUSTER_NAME ?= blipp-cluster
HOST_IP ?= 100.122.207.32
HOST_PORT ?= 8419
NAMESPACE ?= blipp

# Docker image tags
IMAGE_AUTH ?= blipp-auth-service:latest
IMAGE_APP ?= blipp-app:latest
IMAGE_KEYCLOAK ?= quay.io/keycloak/keycloak:26.1.3
IMAGE_POSTGRES ?= postgres:16-alpine

.PHONY: all destroy build import deploy wait status logs cluster-up cluster-down check-prereqs clean

# Default Target: Fully build and deploy the entire production baseline
all: check-prereqs init-env cluster-up build import deploy wait status
	@echo ""
	@echo "=========================================================================="
	@echo "🎉 Blipp Platform is fully running inside the k3d cluster!"
	@echo "   - Expo Web App:       http://$(HOST_IP):$(HOST_PORT)/"
	@echo "   - Keycloak OIDC:      http://$(HOST_IP):$(HOST_PORT)/keycloak"
	@echo "   - FastAPI Swagger UI: http://$(HOST_IP):$(HOST_PORT)/api/docs"
	@echo "   - FastAPI Health API: http://$(HOST_IP):$(HOST_PORT)/api/health"
	@echo "   - Keycloak Discovery: http://$(HOST_IP):$(HOST_PORT)/keycloak/realms/blipp/.well-known/openid-configuration"
	@echo "=========================================================================="

# Destroy Target: Cleanly tear down the cluster and resources
destroy:
	@echo "🛑 Destroying k3d cluster '$(CLUSTER_NAME)'..."
	@k3d cluster delete $(CLUSTER_NAME) || true
	@echo "✅ Cluster and all associated resources destroyed."

# Verify required host CLI tools
check-prereqs:
	@command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required but not installed."; exit 1; }
	@command -v k3d >/dev/null 2>&1 || { echo "❌ k3d is required but not installed."; exit 1; }
	@command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl is required but not installed."; exit 1; }
	@docker info >/dev/null 2>&1 || { echo "❌ Docker daemon is not running or accessible."; exit 1; }
	@echo "✅ Prerequisites check passed."

# Ensure .env exists
init-env:
	@if [ ! -f $(ENV_FILE) ]; then \
		echo "⚙️ Creating $(ENV_FILE) from $(ENV_FILE).example..."; \
		cp $(ENV_FILE).example $(ENV_FILE); \
	fi

# Create k3d cluster with Traefik Ingress mapped to host port without port-forwarding
cluster-up:
	@if ! k3d cluster list | grep -q "^$(CLUSTER_NAME) "; then \
		echo "🚀 Creating k3d cluster '$(CLUSTER_NAME)' with host port $(HOST_PORT)..."; \
		k3d cluster create $(CLUSTER_NAME) \
			--port "$(HOST_PORT):80@loadbalancer" \
			--wait; \
	else \
		echo "ℹ️ Cluster '$(CLUSTER_NAME)' already exists."; \
	fi

# Delete k3d cluster
cluster-down: destroy

# Build all service containers using Docker layer caching
build:
	@echo "📦 Building FastAPI Auth Service container [$(IMAGE_AUTH)]..."
	DOCKER_BUILDKIT=0 docker build -t $(IMAGE_AUTH) ./services/auth
	@echo "📦 Building Expo Frontend container [$(IMAGE_APP)]..."
	DOCKER_BUILDKIT=0 docker build -t $(IMAGE_APP) ./apps/blipp
	@echo "📦 Pulling base images..."
	@docker pull $(IMAGE_KEYCLOAK)
	@docker pull $(IMAGE_POSTGRES)
	@echo "✅ Container builds completed."

# Import images into k3d cluster so no external registry is needed
import:
	@echo "📥 Importing container images into k3d cluster '$(CLUSTER_NAME)'..."
	k3d image import $(IMAGE_AUTH) -c $(CLUSTER_NAME)
	k3d image import $(IMAGE_APP) -c $(CLUSTER_NAME)
	@echo "✅ Images imported."

# Apply Kubernetes manifests
deploy:
	@echo "☸️ Applying Kubernetes manifests to namespace '$(NAMESPACE)'..."
	@kubectl apply -f k8s/namespace.yaml
	@echo "🔐 Generating Secret 'blipp-secrets' from $(ENV_FILE)..."
	@kubectl create secret generic blipp-secrets \
		--namespace=$(NAMESPACE) \
		--from-env-file=$(ENV_FILE) \
		--dry-run=client -o yaml | kubectl apply -f -
	@echo "💾 Deploying PostgreSQL..."
	@kubectl apply -f k8s/postgres/
	@echo "🔑 Deploying Keycloak..."
	@kubectl apply -f k8s/keycloak/
	@echo "⚡ Deploying FastAPI Auth Service..."
	@kubectl apply -f k8s/auth-service/
	@echo "📱 Deploying Blipp Expo Frontend..."
	@kubectl apply -f k8s/blipp-app/
	@echo "🌐 Deploying Traefik Ingress..."
	@kubectl apply -f k8s/ingress/
	@echo "✅ Manifests applied."

# Wait for all deployments to reach ready status
wait:
	@echo "⏳ Waiting for PostgreSQL readiness..."
	@kubectl rollout status deployment/postgres -n $(NAMESPACE) --timeout=120s
	@echo "⏳ Waiting for Keycloak readiness (this can take ~30-60s on initial DB migration)..."
	@kubectl rollout status deployment/keycloak -n $(NAMESPACE) --timeout=180s
	@echo "⏳ Waiting for FastAPI Auth Service readiness..."
	@kubectl rollout status deployment/auth-service -n $(NAMESPACE) --timeout=120s
	@echo "⏳ Waiting for Blipp Expo App readiness..."
	@kubectl rollout status deployment/blipp-app -n $(NAMESPACE) --timeout=120s
	@echo "✅ All microservices are healthy and ready!"

# Show cluster and pod status
status:
	@echo "📊 Cluster Status (Namespace: $(NAMESPACE)):"
	@kubectl get pods,services,ingress -n $(NAMESPACE)

# Tail logs across all services
logs:
	@kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/part-of=blipp --all-containers=true -f --prefix=true

# Clean up dangling images
clean:
	@docker image prune -f
