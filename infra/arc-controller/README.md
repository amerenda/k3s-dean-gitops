# ARC Controller

This directory contains the configuration for the GitHub Actions Runner Controller (ARC) controller component.

## Purpose

The ARC controller manages runner scale sets cluster-wide and handles authentication with GitHub.

## Files

- `values.yaml` - Helm values for the ARC controller
- `externalsecret.yaml` - ExternalSecret for GitHub App credentials (creates `controller-manager` secret used by both controller and runners)

## Configuration

- **Namespace**: `arc-systems`
- **Sync Wave**: 1 (installs early, must be synced before ARC runners)
- **GitHub Auth**: Uses GitHub App authentication via ExternalSecret
- **Secret Name**: `controller-manager` (used by both ARC controller and runner scale sets)

## Sync Order

This application must be synced and healthy before the ARC runners application can be synced. ArgoCD sync waves (wave 1 for controller, wave 5 for runners) ensure this ordering automatically.

## Dependencies

- External Secrets Operator (for GitHub App credentials)
- Bitwarden SecretStore (for credential management)

## Required GitHub App Permissions

Based on [GitHub REST API documentation](https://docs.github.com/en/rest/actions/self-hosted-runners?apiVersion=2022-11-28):

### For Repository-Level Runners (Personal Accounts)
**Repository permissions:**
- Actions: Read and write
- Administration: Read and write
- Metadata: Read-only (automatically selected)

**Organization permissions:**
- Not required for personal accounts (only needed if using organization-level runners)

### For Organization-Level Runners (Organizations Only)
**Repository permissions:**
- Actions: Read and write
- Administration: Read and write
- Metadata: Read-only (automatically selected)

**Organization permissions:**
- **Self-hosted runners**: Read and write (REQUIRED)
- **Organization administration**: Read-only (may be required for registration tokens)

The endpoint `POST /orgs/{org}/actions/runners/registration-token` requires authenticated users to have admin access to the organization. For GitHub Apps, this typically means "Self-hosted runners: Read and write" permission, but some setups may require "Organization administration: Read-only" as well.

**Note:** Personal GitHub accounts cannot use organization-level runners and must use repository-level runners instead.

**Important:** After changing GitHub App permissions, you MUST:
1. Reinstall the app (Install App → Configure → Save)
2. Wait for ExternalSecret to refresh (it refreshes every 1 hour by default)
3. Or manually refresh: `kubectl delete externalsecret controller-manager -n arc-systems` and let ArgoCD recreate it
