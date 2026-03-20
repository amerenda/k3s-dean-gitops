# ARC Runners

This directory contains the configuration for the GitHub Actions Runner Scale Set using the official Helm chart.

## Purpose

The runner scale set deploys self-hosted runners that scale based on workflow demand using the official [gha-runner-scale-set Helm chart](https://docs.github.com/en/actions/tutorials/use-actions-runner-controller/quickstart).

## Files

- `values.yaml` - Helm values for the `gha-runner-scale-set` chart
- `externalsecret.yaml` - ExternalSecret for GitHub App credentials in `arc-runners` namespace

## Configuration

- **Namespace**: `arc-runners`
- **Sync Wave**: 5 (installs after controller and external-secrets)
- **Runner Labels**: `self-hosted`, `linux`, `arc-runner-set` (matches `runs-on` in workflows)
- **Scaling**: 1-3 runners based on demand (managed by autoscalingRunnerSet in Helm chart)
- **Installation Name**: `arc-runner-set` (used in workflow `runs-on` field)

## Dependencies

- **ARC Controller** (must be synced and healthy first - see `arc-controller` application)
- **ExternalSecret** in `arc-runners` namespace (sync wave 0, creates `controller-manager` secret)
- GitHub App credentials (via ExternalSecret `controller-manager` in `arc-runners` namespace)

## Helm Chart

This application uses the official Helm chart:
- **Chart**: `oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set`
- **Chart Version**: `latest` (pinned to latest stable)

## Sync Order

1. **ARC Controller** (wave 1) - Must be synced first
2. **ExternalSecret** (wave 0) - Creates GitHub App credentials secret in `arc-runners` namespace
3. **Runner Scale Set** (wave 5) - Helm chart installs after dependencies are ready

## GitHub App Authentication

The Helm chart authenticates using GitHub App credentials stored in the `controller-manager` secret in the `arc-runners` namespace. The secret is created by the ExternalSecret and contains:
- `github_app_id`
- `github_app_installation_id`
- `github_app_private_key`

These credentials are fetched from Bitwarden via the External Secrets Operator.

## Usage in Workflows

Use the runner in your GitHub Actions workflows:

```yaml
jobs:
  my-job:
    runs-on: arc-runner-set
    steps:
      - run: echo "Running on self-hosted runner"
```
