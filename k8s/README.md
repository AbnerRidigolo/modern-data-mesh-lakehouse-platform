# Deploy em Kubernetes

Manifestos **Kustomize** (base + overlays `dev`/`prod`) para rodar a plataforma
completa em Kubernetes. Reproduz a topologia do `docker-compose.yml` com práticas
de produção: probes de liveness/readiness, requests/limits de recursos,
`StatefulSet` + PVC para os stores com estado, volume `ReadWriteMany`
compartilhado, `HorizontalPodAutoscaler` na API, `Ingress` e segregação
ConfigMap/Secret.

## Estrutura

```
k8s/
├── base/                      # manifestos canônicos (24 recursos)
│   ├── namespace.yaml
│   ├── configmap.yaml         # config não-sensível (hosts, portas, endpoints)
│   ├── secret.example.yaml    # ⚠️ segredos DEV — troque em produção
│   ├── storage.yaml           # PVC RWX compartilhado (/storage)
│   ├── postgres/redis/minio/qdrant.yaml   # StatefulSets + PVC
│   ├── mlflow/airflow/api/frontend.yaml   # Deployments (+ Job de init do Airflow)
│   ├── ingress.yaml           # data-mesh.local + api.data-mesh.local
│   ├── hpa.yaml               # autoscaling da API por CPU
│   └── kustomization.yaml
└── overlays/
    ├── dev/                   # 1 réplica, recursos enxutos, imagens :dev
    └── prod/                  # 3 réplicas, limites maiores, HPA amplo, Ingress TLS
```

## Pré-requisitos

- Um cluster (kind, minikube ou gerenciado) e `kubectl`.
- Um **ingress controller** (ex.: `ingress-nginx`).
- **metrics-server** para o HPA (addon no minikube; instalação manual no kind).
- Para o volume compartilhado `ReadWriteMany`: cluster de nó único (kind/minikube
  atendem via hostPath) ou um provisionador RWX (NFS, EFS, CephFS, Azure Files).

## Build das imagens

Três imagens são construídas a partir do repositório. **O frontend embute a URL
da API em build time**, então passe o build-arg apontando para o host do Ingress:

```bash
# a partir da raiz do repositório
docker build -t data-mesh/api:dev -f app/Dockerfile .
docker build -t data-mesh/airflow:dev -f Dockerfile .
docker build -t data-mesh/frontend:dev \
  --build-arg VITE_API_URL=http://api.data-mesh.local ./frontend
```

Carregue-as no cluster local (sem registry):

```bash
# kind
kind load docker-image data-mesh/api:dev data-mesh/airflow:dev data-mesh/frontend:dev
# minikube
minikube image load data-mesh/api:dev data-mesh/airflow:dev data-mesh/frontend:dev
```

## Deploy

```bash
# renderiza e revisa
kubectl kustomize k8s/overlays/dev

# aplica o overlay de desenvolvimento
kubectl apply -k k8s/overlays/dev

# acompanha a subida
kubectl -n data-mesh get pods -w
```

O `Job` `airflow-init` roda a migração do banco e cria o usuário admin antes do
webserver/scheduler ficarem prontos.

### Acesso local

Aponte os hosts do Ingress para o cluster em `/etc/hosts`:

```
127.0.0.1  data-mesh.local api.data-mesh.local
```

- Portal: <http://data-mesh.local>
- API (Swagger): <http://api.data-mesh.local/docs>

(`minikube tunnel` ou o port-forward do ingress-nginx podem ser necessários
dependendo do driver.)

### AI Copilot

O Copilot fica desabilitado até `ANTHROPIC_API_KEY` ser fornecido. Não versione a
chave — injete-a no Secret em runtime:

```bash
kubectl -n data-mesh create secret generic platform-secrets \
  --from-literal=ANTHROPIC_API_KEY=sk-ant-... \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n data-mesh rollout restart deployment/api
```

## Produção

`kubectl apply -k k8s/overlays/prod` aplica: 3 réplicas de API/frontend, HPA de
3→10, limites de recurso maiores, imagens pinadas por versão (sem `:latest`) e
Ingress com TLS (via `cert-manager`). **Antes**: substitua o `secret.example.yaml`
por segredos reais gerenciados fora do git (External Secrets Operator, Sealed
Secrets, Vault ou SOPS) e ajuste os hosts em `overlays/prod`.

## Validação sem cluster

```bash
kubectl kustomize k8s/overlays/dev   # renderiza e valida a estrutura Kustomize
kubectl kustomize k8s/overlays/prod
```
