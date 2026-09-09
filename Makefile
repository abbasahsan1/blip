CLUSTER_NAME := blipp-cluster
NAMESPACE    := blipp
SHELL        := /bin/bash

IMAGES := blipp-auth:latest \
          blipp-content-ingest:latest \
          blipp-feed:latest \
          blipp-social-graph:latest \
          blipp-transcode-worker:latest \
          blipp-analytics-worker:latest

.PHONY: help all upgrade destroy cluster-up k3d-import build-all build-auth build-ingest \
        build-feed build-social build-transcode build-analytics k8s-init k8s-deploy \
        k8s-status port-forward port-forward-stop dev-mobile

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ==============================================================================
# Top-Level Autonomous Lifecycle Targets
# ==============================================================================

all: cluster-up build-all k3d-import k8s-init k8s-deploy ## Setup everything from scratch (cluster, images, storage, workloads, port-forwards)
	@echo "Waiting for core microservices to reach Ready state..."
	@kubectl rollout status deployment/auth-service -n $(NAMESPACE) --timeout=120s || true
	@kubectl rollout status deployment/content-ingest -n $(NAMESPACE) --timeout=120s || true
	@kubectl rollout status deployment/feed -n $(NAMESPACE) --timeout=120s || true
	@kubectl rollout status deployment/social-graph -n $(NAMESPACE) --timeout=120s || true
	@$(MAKE) port-forward
	@echo "=================================================================="
	@echo "  Blipps Platform is fully deployed and accessible on localhost!"
	@echo "=================================================================="
	@echo "  - Auth:           http://localhost:8000"
	@echo "  - Content Ingest: http://localhost:8001"
	@echo "  - Feed:           http://localhost:8002"
	@echo "  - Social Graph:   http://localhost:8003"
	@echo "  - MinIO S3:       http://localhost:9000"
	@echo "  - Keycloak:       http://localhost:8080"
	@echo "  - Redis:          localhost:6379"
	@echo "------------------------------------------------------------------"
	@echo "Launch mobile/web client with: cd apps/blipp && npx expo start"

upgrade: build-all k3d-import ## Non-blocking rolling upgrade of running application services
	@echo "Applying updated manifests to namespace $(NAMESPACE)..."
	@kubectl apply -f k8s/secrets.yaml
	@kubectl apply -f k8s/auth/
	@kubectl apply -f k8s/content-ingest/
	@kubectl apply -f k8s/feed/
	@kubectl apply -f k8s/social-graph/
	@kubectl apply -f k8s/transcode-worker/
	@kubectl apply -f k8s/analytics-worker/
	@kubectl apply -f k8s/ingress/
	@echo "Triggering zero-downtime rolling restart..."
	@kubectl rollout restart deployment/auth-service -n $(NAMESPACE)
	@kubectl rollout restart deployment/content-ingest -n $(NAMESPACE)
	@kubectl rollout restart deployment/feed -n $(NAMESPACE)
	@kubectl rollout restart deployment/social-graph -n $(NAMESPACE)
	@kubectl rollout restart deployment/transcode-worker -n $(NAMESPACE)
	@kubectl rollout restart deployment/analytics-worker -n $(NAMESPACE)
	@echo "Upgrade complete. Workloads are rolling forward."

destroy: port-forward-stop ## Destroy everything (cluster, workloads, storage, and port-forwards)
	@echo "Stopping port-forwards..."
	@$(MAKE) port-forward-stop
	@if k3d cluster list 2>/dev/null | grep -E "^$(CLUSTER_NAME)\s" >/dev/null 2>&1; then \
		echo "Deleting k3d cluster '$(CLUSTER_NAME)'..."; \
		k3d cluster delete $(CLUSTER_NAME); \
	else \
		echo "Deleting namespace '$(NAMESPACE)'..."; \
		kubectl delete namespace $(NAMESPACE) --ignore-not-found=true; \
	fi
	@echo "Environment completely destroyed."

# ==============================================================================
# Cluster Management & Image Import
# ==============================================================================

cluster-up: ## Create local k3d cluster if it does not exist
	@if ! k3d cluster list 2>/dev/null | grep -E "^$(CLUSTER_NAME)\s" >/dev/null 2>&1; then \
		echo "Creating k3d cluster '$(CLUSTER_NAME)'..."; \
		k3d cluster create $(CLUSTER_NAME) --wait; \
	else \
		echo "k3d cluster '$(CLUSTER_NAME)' is already running."; \
	fi
	@kubectl config use-context k3d-$(CLUSTER_NAME) >/dev/null 2>&1 || true

k3d-import: ## Import all locally built Docker images into the k3d cluster
	@echo "Importing container images into k3d cluster '$(CLUSTER_NAME)'..."
	@k3d image import $(IMAGES) -c $(CLUSTER_NAME)
	@echo "All images imported successfully."

# ==============================================================================
# Container Builds (Context pinned to repository root for libs/common)
# ==============================================================================

build-auth:
	docker build -t blipp-auth:latest -t blipp-auth-service:latest -f services/auth/Dockerfile .

build-ingest:
	docker build -t blipp-content-ingest:latest -f services/content_ingest/Dockerfile .

build-feed:
	docker build -t blipp-feed:latest -f services/feed/Dockerfile .

build-social:
	docker build -t blipp-social-graph:latest -f services/social_graph/Dockerfile .

build-transcode:
	docker build -t blipp-transcode-worker:latest -f services/transcode_worker/Dockerfile .

build-analytics:
	docker build -t blipp-analytics-worker:latest -f services/analytics_worker/Dockerfile .

build-all: build-auth build-ingest build-feed build-social build-transcode build-analytics ## Build all Docker images

# ==============================================================================
# Kubernetes Infrastructure & Deployments
# ==============================================================================

k8s-init: ## Ensure namespace, secrets, and PVC storage exist
	@kubectl apply -f k8s/namespace.yaml
	@kubectl apply -f k8s/secrets.yaml
	@kubectl apply -f k8s/postgres/pvc.yaml
	@kubectl apply -f k8s/minio/pvc.yaml
	@kubectl apply -f k8s/redis/pvc.yaml
	@kubectl apply -f k8s/nats/pvc.yaml
	@kubectl apply -f k8s/gorse/pvc.yaml

k8s-deploy: ## Apply infrastructure, microservices, workers, and ingress manifests
	# Stateful infrastructure
	@kubectl apply -f k8s/postgres/
	@kubectl apply -f k8s/minio/
	@kubectl apply -f k8s/nats/
	@kubectl apply -f k8s/redis/
	@kubectl apply -f k8s/keycloak/
	@kubectl apply -f k8s/gorse/
	# Core microservices
	@kubectl apply -f k8s/auth/
	@kubectl apply -f k8s/content-ingest/
	@kubectl apply -f k8s/feed/
	@kubectl apply -f k8s/social-graph/
	# Batch workers
	@kubectl apply -f k8s/transcode-worker/
	@kubectl apply -f k8s/analytics-worker/
	# Ingress routing
	@kubectl apply -f k8s/ingress/

k8s-status: ## Show status of all cluster pods, services, and PVCs
	@kubectl get pods,svc,pvc -n $(NAMESPACE) -o wide

# ==============================================================================
# Local Networking & Port Forwarding
# ==============================================================================

port-forward: port-forward-stop ## Start background port-forwarding on all interfaces
	@echo "Establishing port-forwards for namespace: $(NAMESPACE) on 0.0.0.0..."
	@kubectl port-forward --address 0.0.0.0 -n $(NAMESPACE) svc/auth-service 8000:8000 > /dev/null 2>&1 &
	@kubectl port-forward --address 0.0.0.0 -n $(NAMESPACE) svc/content-ingest-service 8001:8001 > /dev/null 2>&1 &
	@kubectl port-forward --address 0.0.0.0 -n $(NAMESPACE) svc/feed-service 8002:8002 > /dev/null 2>&1 &
	@kubectl port-forward --address 0.0.0.0 -n $(NAMESPACE) svc/social-graph-service 8003:8003 > /dev/null 2>&1 &
	@kubectl port-forward --address 0.0.0.0 -n $(NAMESPACE) svc/minio 9000:9000 > /dev/null 2>&1 &
	@kubectl port-forward --address 0.0.0.0 -n $(NAMESPACE) svc/keycloak 8080:8080 > /dev/null 2>&1 &
	@kubectl port-forward --address 0.0.0.0 -n $(NAMESPACE) svc/redis 6379:6379 > /dev/null 2>&1 &
	@echo "Active endpoints bound to 0.0.0.0:"
	@echo "  - Auth:           http://localhost:8000"
	@echo "  - Content Ingest: http://localhost:8001"
	@echo "  - Feed:           http://localhost:8002"
	@echo "  - Social Graph:   http://localhost:8003"
	@echo "  - MinIO:          http://localhost:9000"
	@echo "  - Keycloak:       http://localhost:8080"
	@echo "  - Redis:          localhost:6379"

port-forward-stop: ## Kill any active kubectl port-forward processes safely
	@-pkill -f "[k]ubectl port-forward" 2>/dev/null || true
	@echo "Port-forwards stopped."

dev-mobile: ## Run mobile environment auto-configuration script
	./scripts/dev-mobile.sh