# k3s-dean-gitops

GitOps repository for a k3s home lab cluster running on Raspberry Pi nodes. ArgoCD watches this repo and automatically reconciles all infrastructure and application state.

## Architecture

```
root-app.yaml (ArgoCD App-of-Apps)
├── infra/                    Infrastructure components
│   ├── flannel               CNI networking (sync-wave 0)
│   ├── metallb               Load balancer (sync-wave 0)
│   ├── cert-manager          TLS certificates via Let's Encrypt + DigitalOcean DNS (sync-wave 0)
│   ├── external-secrets      Bitwarden secret sync (sync-wave 2)
│   ├── longhorn              Distributed storage with S3 backups (sync-wave 3)
│   ├── traefik               Ingress controller
│   ├── external-dns          DNS record management (amer.home + amer.dev)
│   ├── dns                   BIND9 authoritative DNS
│   ├── monitoring             Prometheus + Grafana (kube-prometheus-stack)
│   ├── tailscale             VPN access
│   ├── reloader              Auto-restart on config changes
│   ├── arc-controller        GitHub Actions Runner Controller
│   └── arc-runners-*         Per-repo self-hosted runner scale sets
│
├── apps/                     Application deployments
│   ├── home-assistant        Home automation
│   ├── pihole                DNS ad-blocking
│   ├── unifi-network-application  UniFi network controller + MongoDB
│   ├── llm-manager           GPU inference manager (backend + UI + PostgreSQL)
│   ├── llm-agents            Piper TTS agent
│   ├── ecdysis               Moltbook agent management UI
│   └── moltbook              Proxy to Moltbook on GPU host
│
└── bootstrap/                One-time manual setup
    ├── argocd/values.yaml    ArgoCD Helm values
    ├── appprojects.yaml      infra + application AppProjects
    ├── argocd-repo-secret.yaml   GitHub PAT for repo access
    └── bitwarden-credentials-secret.yaml  External Secrets token
```

ArgoCD uses **sync waves** to control deployment order: networking and certificates first (wave 0), then secret management (wave 2), storage (wave 3), and finally applications (wave 5+). All applications have automated sync with pruning and self-healing enabled.

## Bootstrap

Bootstrapping a new cluster requires the Ansible playbooks (separate repo) plus manual secret setup.

### 1. Provision nodes with Ansible

```bash
# In the ansible-playbooks repo
ansible-playbook -i inventory/inventory.ini all.yml
```

This installs k3s, sets up HA controllers, and deploys ArgoCD with the Helm values from `bootstrap/argocd/values.yaml`.

### 2. Apply bootstrap secrets

```bash
# ArgoCD repo credentials (update PAT first)
kubectl apply -f bootstrap/argocd-repo-secret.yaml

# AppProjects (required before any app can sync)
kubectl apply -f bootstrap/appprojects.yaml

# Bitwarden token for External Secrets (update token first)
kubectl apply -f bootstrap/bitwarden-credentials-secret.yaml
```

### 3. Apply the root application

```bash
kubectl apply -f root-app.yaml
```

ArgoCD will discover and deploy everything else automatically.

## Deploying a New Application

1. Create a directory under `apps/<app-name>/` with your Kubernetes manifests (Deployment, Service, Ingress, etc.).

2. Add an ArgoCD `Application` resource to `root-app.yaml`:

```yaml
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: app-<app-name>
  namespace: default
  annotations:
    argocd.argoproj.io/sync-wave: "5"
  finalizers:
    - resources-finalizer.argocd.argoproj.io/background
spec:
  project: application
  source:
    repoURL: https://github.com/amerenda/k3s-dean-gitops.git
    targetRevision: main
    path: apps/<app-name>
  destination:
    server: https://kubernetes.default.svc
    namespace: <app-name>
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
    retry:
      limit: 5
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m
```

3. For Helm-based apps, use `sources` with a chart repo and a `$values` ref (see `app-pihole` or `infra-longhorn` in `root-app.yaml` for examples).

4. If the app needs secrets, add an `ExternalSecret` resource that pulls from Bitwarden via the `bitwarden-secretstore` ClusterSecretStore.

5. Push to `main`. ArgoCD will pick up the changes automatically.

## CI/CD

Application repos (ecdysis, llm-agents, llm-manager, etc.) each have their own CI pipelines that:

1. **Build** a Docker image on push to `main` (using Kaniko on self-hosted ARC runners).
2. **Open a PR** against this gitops repo, updating the image tag in the relevant deployment manifest.
3. **Merging the PR** triggers ArgoCD to roll out the new version.

This keeps all cluster state in Git. No images are deployed without a corresponding commit in this repo.

### Self-hosted runners

GitHub Actions run on ARC (Actions Runner Controller) deployed in-cluster. Each application repo has its own runner scale set (`infra/arc-runners-*`) with per-repo GitHub App credentials synced via External Secrets.

## Secrets Management

All secrets are stored in Bitwarden and synced into the cluster by the External Secrets Operator. The flow is:

```
Bitwarden --> ClusterSecretStore --> ExternalSecret --> k8s Secret --> Pod env/volume
```

Never commit real secrets to this repo. Use `ExternalSecret` resources that reference Bitwarden secret names.
