# k3s-dean-gitops — Agent Rules

## What this repo is

GitOps manifests for all stateless k3s workloads. ArgoCD watches this repo and syncs changes to the cluster automatically.

## Golden rule: never hand-edit generated manifests

Manifests under `apps/<name>/generated/` are written by `app-factory` (`make create-app`). Hand-editing them will be overwritten on the next `provision_app` run. If you need to change something in a generated manifest, update the TOML spec and re-run `provision_app`.

Supplementary files (`configmap.yaml`, CRDs, additional Deployments) live directly in `apps/<name>/` alongside the `generated/` subdirectory. These are hand-maintained and are never touched by `app-factory`.

## How to deploy a new app

1. `scaffold_app(name, description)` — creates `app-factory/apps/<name>.toml`
2. `provision_app(name)` — validates, runs Tofu, generates manifests into this repo
3. `open_deploy_pr(name, title)` — commits and opens PR (amerenda-coder bot)

Never skip steps or call `make create-app` directly — go through the `infra-mcp` MCP tools.

## Secrets — hard rules

- **No secrets in this repo.** If you find yourself writing a password, token, or key in any YAML file, stop immediately and use ExternalSecrets instead.
- All secrets flow: BWS → ExternalSecrets operator → k8s Secret → Pod env var.
- `ExternalSecret` resources reference keys by `bws_name` (the BWS key name). Never hardcode the BWS secret UUID.

## UAT vs prod — deployment pipeline

- **UAT manifests** live in `apps/<name>/<component>-uat/` — committed directly to `main`. ArgoCD auto-syncs UAT on every push.
- **Prod manifests** live in `apps/<name>/<component>/` — only changed via a human-approved PR. Never auto-merge prod.
- The `uat-applicationset.yaml` deploys UAT automatically when a PR with the `deploy:<name>` label is open.

## git identity for bot commits

All agent commits must use the amerenda-coder GitHub App identity:
```
GIT_AUTHOR_NAME=amerenda-coder[bot]
GIT_AUTHOR_EMAIL=amerenda-coder[bot]@users.noreply.github.com
```

Use `open_deploy_pr` from infra-mcp — it handles identity and token auth automatically.

## ArgoCD apps

The `root-app.yaml` and `uat-applicationset.yaml` in the repo root are the ArgoCD entry points. New apps are registered by `app-factory` generate.py — never add entries by hand.
