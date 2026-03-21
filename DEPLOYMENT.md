# Deployment Guide

How changes flow from code to production in this cluster.

## Architecture

```
[App Repo]                    [GitOps Repo]              [Cluster]
 push to main                  PR with new image tag       ArgoCD syncs
 ──────────────►  CI builds  ──────────────────────►  ──────────────────►  Pods updated
                  + pushes                              auto-merge
                  image
```

## End-to-End Flow

1. Developer pushes code to an app repo (e.g., `amerenda/ecdysis`)
2. GitHub Actions CI runs tests, builds a Docker image, pushes to Docker Hub
3. CI creates a PR to `amerenda/k3s-dean-gitops` updating the image tag
4. PR auto-merges (after validation)
5. ArgoCD detects the change and syncs the new deployment
6. New pod rolls out with the updated image

**Time from push to deployed: ~3-5 minutes**

## Repo Responsibilities

| Repo | What it does | CI output |
|------|-------------|-----------|
| `k3s-dean-gitops` | All k8s manifests, ArgoCD root-app | HA config checks, manifest validation |
| `llm-manager` | GPU resource manager + queue scheduler | `amerenda/llm-manager:backend-*`, `:ui-*` |
| `ecdysis` | Moltbook agent management UI | `amerenda/ecdysis:frontend-*` |
| `llm-agents` | LLM agent services (piper TTS) | `amerenda/llm-agents:piper-*` |
| `k3s-runners` | Custom CI runner images | `amerenda/k3s-runners:home-assistant`, `:kaniko` |
| `ansible-playbooks` | Cluster provisioning | No images (Ansible only) |

## How to Deploy a New App

### 1. Create the app repo

```bash
gh repo create amerenda/<app-name> --public
```

### 2. Add a Dockerfile

Your app needs a `Dockerfile` that produces a runnable container.

### 3. Add CI workflow

Create `.github/workflows/build.yaml`:

```yaml
name: Build and Deploy
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  IMAGE: amerenda/<app-name>
  GITOPS_REPO: amerenda/k3s-dean-gitops

jobs:
  test:
    runs-on: arc-runner-set
    container:
      image: <test-image>  # e.g., node:20-alpine, python:3.12-slim
    steps:
      - uses: actions/checkout@v4
      - run: <your test commands>

  build:
    needs: test
    if: github.event_name != 'pull_request'
    runs-on: arc-runner-set
    container:
      image: amerenda/k3s-runners:kaniko
    steps:
      - uses: actions/checkout@v4
      - name: Set tag
        id: tag
        shell: bash
        run: echo "tag=sha-${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
      - name: Build and push
        shell: bash
        env:
          TAG: ${{ steps.tag.outputs.tag }}
          DOCKERHUB_USERNAME: ${{ secrets.DOCKERHUB_USERNAME }}
          DOCKERHUB_TOKEN: ${{ secrets.DOCKERHUB_TOKEN }}
        run: |
          mkdir -p /kaniko/.docker
          echo '{"auths":{"https://index.docker.io/v1/":{"username":"'"${DOCKERHUB_USERNAME}"'","password":"'"${DOCKERHUB_TOKEN}"'"}}}' > /kaniko/.docker/config.json
          /kaniko/executor \
            --context="${GITHUB_WORKSPACE}" \
            --dockerfile=Dockerfile \
            --destination="${IMAGE}:${TAG}" \
            --destination="${IMAGE}:latest"

  deploy:
    needs: build
    if: github.event_name != 'pull_request'
    runs-on: arc-runner-set
    container:
      image: ubuntu:22.04
      env:
        GITOPS_PAT: ${{ secrets.GITOPS_PAT }}
    steps:
      - run: apt-get update && apt-get install -y git curl
      - name: Raise gitops PR
        shell: bash
        env:
          TAG: ${{ needs.build.outputs.tag }}
        run: |
          git clone https://x-access-token:${GITOPS_PAT}@github.com/${GITOPS_REPO}.git /tmp/gitops
          cd /tmp/gitops
          BRANCH="deploy/<app-name>-${TAG}"
          git checkout -b "${BRANCH}"
          sed -i "s|amerenda/<app-name>:[^ ]*|amerenda/<app-name>:${TAG}|g" apps/<app-name>/deployment.yaml
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add -A && git diff --cached --quiet && exit 0
          git commit -m "deploy: <app-name> ${TAG}"
          git push origin "${BRANCH}"
          curl -s -X POST -H "Authorization: token ${GITOPS_PAT}" \
            "https://api.github.com/repos/${GITOPS_REPO}/pulls" \
            -d '{"title":"deploy: <app-name> '"${TAG}"'","head":"'"${BRANCH}"'","base":"main"}'
```

### 4. Set repo secrets

```bash
gh secret set DOCKERHUB_USERNAME --repo amerenda/<app-name> --body "amerenda"
gh secret set DOCKERHUB_TOKEN --repo amerenda/<app-name> --body "<token>"
gh secret set GITOPS_PAT --repo amerenda/<app-name> --body "<pat>"
```

### 5. Install the GitHub App

The `k3s-arc-runners` GitHub App must be installed on the repo for ARC runners to pick up jobs.

### 6. Add k8s manifests to gitops

Create `apps/<app-name>/` in this repo with:

```
apps/<app-name>/
  deployment.yaml
  service.yaml
  ingress.yaml          # if externally accessible
  namespace.yaml        # if new namespace needed
  externalsecret.yaml   # if needs Bitwarden secrets
```

### 7. Add to root-app.yaml

Add an Application resource to `root-app.yaml`:

```yaml
- apiVersion: argoproj.io/v1alpha1
  kind: Application
  metadata:
    name: app-<app-name>
    namespace: default
    annotations:
      argocd.argoproj.io/sync-wave: "5"
    finalizers:
      - resources-finalizer.argocd.argoproj.io
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
```

### 8. Push and verify

```bash
git add apps/<app-name>/ root-app.yaml
git commit -m "feat: add <app-name> app"
git push origin main
# ArgoCD will create the namespace and deploy the app
kubectl get pods -n <app-name>
```

## Using the LLM Queue

If your app needs LLM inference, use the queue API instead of calling Ollama directly:

```python
import httpx

BACKEND = "http://llm-manager-backend.llm-manager.svc.cluster.local:8081"

# Submit a job
resp = httpx.post(f"{BACKEND}/api/queue/submit", json={
    "model": "qwen2.5:7b",
    "messages": [{"role": "user", "content": "Hello"}],
    "metadata": {"app": "my-app"}
}, headers={"Authorization": f"Bearer {API_KEY}"})
job_id = resp.json()["job_id"]

# Wait for result (SSE)
with httpx.stream("GET", f"{BACKEND}/api/queue/jobs/{job_id}/wait") as stream:
    for line in stream.iter_lines():
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if data["status"] == "completed":
                result = data["result"]
                break
```

## ArgoCD Access

- **UI**: https://argocd.amer.dev
- **CLI**: `argocd app list --server argocd.amer.dev --grpc-web --insecure`

## Troubleshooting

### App stuck in OutOfSync
```bash
kubectl patch application <app-name> -n default --type merge \
  -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

### CI job queued but not running
Check if the ARC runner listener exists:
```bash
kubectl get pods -n arc-systems | grep listener
```

### Image not pulling
Check the image tag in the deployment:
```bash
kubectl get deployment <app> -n <ns> -o jsonpath='{.spec.template.spec.containers[0].image}'
```

### ExternalSecrets not syncing
```bash
kubectl get externalsecret -A
kubectl get clustersecretstore
```
