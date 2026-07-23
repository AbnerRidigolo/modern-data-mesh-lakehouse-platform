# Atalhos para build, load e deploy no Kubernetes.
# Uso: make -C k8s <alvo>  (ou cd k8s && make <alvo>)

REGISTRY ?= data-mesh
TAG ?= dev
OVERLAY ?= dev
NS ?= data-mesh
API_HOST ?= http://api.data-mesh.local
ROOT := ..

.PHONY: help build load deploy render diff status logs delete

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

build: ## Builda as três imagens (api, airflow, frontend)
	docker build -t $(REGISTRY)/api:$(TAG) -f $(ROOT)/app/Dockerfile $(ROOT)
	docker build -t $(REGISTRY)/airflow:$(TAG) -f $(ROOT)/Dockerfile $(ROOT)
	docker build -t $(REGISTRY)/frontend:$(TAG) --build-arg VITE_API_URL=$(API_HOST) $(ROOT)/frontend

load: ## Carrega as imagens no cluster local (kind). Use LOADER=minikube p/ minikube
	@if [ "$(LOADER)" = "minikube" ]; then \
	  minikube image load $(REGISTRY)/api:$(TAG) $(REGISTRY)/airflow:$(TAG) $(REGISTRY)/frontend:$(TAG); \
	else \
	  kind load docker-image $(REGISTRY)/api:$(TAG) $(REGISTRY)/airflow:$(TAG) $(REGISTRY)/frontend:$(TAG); \
	fi

render: ## Renderiza o overlay (OVERLAY=dev|prod)
	kubectl kustomize overlays/$(OVERLAY)

deploy: ## Aplica o overlay no cluster
	kubectl apply -k overlays/$(OVERLAY)

diff: ## Diff contra o estado atual do cluster
	kubectl diff -k overlays/$(OVERLAY) || true

status: ## Mostra pods, services e HPA do namespace
	kubectl -n $(NS) get pods,svc,hpa,ingress

logs: ## Segue os logs da API (POD=<nome> para outro pod)
	kubectl -n $(NS) logs -l app.kubernetes.io/name=api -f --tail=100

delete: ## Remove o overlay do cluster
	kubectl delete -k overlays/$(OVERLAY)
