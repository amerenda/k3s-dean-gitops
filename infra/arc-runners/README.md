# ARC Runners

GitHub Actions self-hosted runners managed by ARC (Actions Runner Controller) on the k3s cluster.

## Runner Types

| Type | Label (`runs-on`) | Docker Access | Use Case |
|------|-------------------|---------------|----------|
| **build** | `arc-runner-set` | Yes (host socket) | Docker image builds, anything needing Docker |
| **ci** | `arc-runner-set` | No | Tests, linting, deploy PRs, API calls |

Build runners use **node affinity** so they can schedule on **murderbot** or **archlinux** (`kubernetes.io/hostname` `In` `[murderbot, archlinux]`). The scheduler picks any node that fits resources and taints; when **murderbot** is healthy it shares load with **archlinux** instead of replacing it.

If **archlinux** still has the legacy `archlinux=true:NoSchedule` taint, run Ansible `post-k3s.yml` (it removes that taint on `archlinux_k3s` hosts) so ARC pods can land there.

Build runners mount the host Docker socket (`/var/run/docker.sock`) — no DinD. This gives native build speed with persistent layer cache across all jobs.

**Docker socket GID:** `supplementalGroups: [989]` matches **murderbot** (Debian) `docker` group. On **archlinux**, run `getent group docker | cut -d: -f3`; if it differs, add that GID to the list (for example `[989, 952]`) in each `infra/arc-runners-*/values.yaml` that mounts the socket so the same pod spec works on both hosts.

## Secrets

All secrets come from Bitwarden Secrets Manager via ExternalSecrets:

| Secret | K8s Secret | Keys |
|--------|-----------|------|
| GitHub App (ARC auth) | `controller-manager` | `github_app_id`, `github_app_installation_id`, `github_app_private_key` |
| CI credentials | `runner-ci-credentials` | `DOCKERHUB_TOKEN`, `GITOPS_PAT` |

**No secrets in GitHub.** Workflows use `$DOCKERHUB_TOKEN` (shell env var), not `${{ secrets.DOCKERHUB_TOKEN }}`.

## Adding a New Repo

1. **Create the runner directory:**
   ```bash
   cp -r infra/arc-runners-ecdysis infra/arc-runners-<repo>
   ```

2. **Update `values.yaml`:**
   - `githubConfigUrl` → `https://github.com/amerenda/<repo>`
   - `runnerScaleSetName` → `arc-runner-set` (keep consistent for now)
   - `namespaceOverride` → `arc-runners-<repo>`
   - For CI-only: remove `securityContext`, `DOCKER_HOST`, docker-sock volume/mount

3. **Update `externalsecret.yaml`:**
   - No changes needed if using same BWS secrets (controller-manager + runner-ci-credentials)
   - For repos with unique secrets (like tailscale-acl), add the extra keys

4. **Add ArgoCD Application to `root-app.yaml`:**
   ```yaml
   ---
   # Infrastructure: ARC Runner Scale Set — <repo>
   apiVersion: argoproj.io/v1alpha1
   kind: Application
   metadata:
     name: infra-arc-runners-<repo>
     namespace: default
     annotations:
       argocd.argoproj.io/sync-wave: "5"
     finalizers:
       - resources-finalizer.argocd.argoproj.io/background
   spec:
     project: infra
     sources:
       - repoURL: oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
         path: .
         targetRevision: 0.13.0
         helm:
           valueFiles:
             - $values/infra/arc-runners-<repo>/values.yaml
       - repoURL: https://github.com/amerenda/k3s-dean-gitops.git
         targetRevision: main
         ref: values
       - repoURL: https://github.com/amerenda/k3s-dean-gitops.git
         targetRevision: main
         path: infra/arc-runners-<repo>
     destination:
       server: https://kubernetes.default.svc
       namespace: arc-runners-<repo>
     syncPolicy:
       automated:
         prune: true
         selfHeal: true
       syncOptions:
         - CreateNamespace=true
         - PrunePropagationPolicy=foreground
         - ServerSideApply=true
       retry:
         limit: 5
         backoff:
           duration: 5s
           factor: 2
           maxDuration: 3m
     ignoreDifferences:
     - group: "actions.github.com"
       kind: AutoscalingRunnerSet
       jsonPointers:
       - /status/pendingEphemeralRunners
       - /status/currentRunners
   ```

5. **In the app repo workflow**, use:
   ```yaml
   runs-on: arc-runner-set
   ```

6. **Push to k3s-dean-gitops main** — ArgoCD auto-syncs.

## Architecture

```
Mac Mini (arm64)          murderbot + archlinux k3s agents (amd64 build pool)
┌──────────────────────┐            ┌─────────────────────────────┐
│ myoung34/github-runner│            │ ARC Controller (arc-systems) │
│ Labels: mac-mini,arm64│            │                             │
│ Docker: host socket   │            │ amd64 build runners:        │
│ Repos: all app repos  │            │   node: murderbot | archlinux
│                       │            │   - ecdysis, llm-manager…   │
│ Handles: arm64 builds │            │ Docker: host socket          │
│                       │            │                             │
│                       │            │ amd64 CI runners:           │
│                       │            │   - k3s-dean-gitops         │
│                       │            │   - tailscale-acl           │
│                       │            │ Docker: none                │
└──────────────────────┘            └─────────────────────────────┘
```
