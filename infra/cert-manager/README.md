# cert-manager Infrastructure

This directory contains the Helm chart configuration for cert-manager v1.19.0.

## Overview

cert-manager is a Kubernetes add-on to automate the management and issuance of TLS certificates from various issuing sources. It will ensure certificates are valid and up to date, and attempt to renew certificates at an appropriate time before expiry.

## Configuration

The configuration is defined in `values.yaml` and includes:

- **CRD Installation**: Automatically installs cert-manager CRDs
- **Security**: Runs with non-root user and proper security contexts
- **Resources**: Configured with appropriate CPU and memory limits
- **Monitoring**: Prometheus metrics and health checks enabled
- **RBAC**: Proper role-based access control configured

## Key Features

- Automatic TLS certificate management
- Support for Let's Encrypt and other ACME providers
- Integration with various DNS providers
- Prometheus metrics and monitoring
- Webhook validation for certificate requests

## Usage

This application is managed by ArgoCD and will be automatically deployed to the `cert-manager` namespace.

## Dependencies

- Kubernetes cluster with RBAC enabled
- Helm 3.x
- ArgoCD for GitOps deployment

## Certificate Issuers

This setup includes a pre-configured ClusterIssuer for Let's Encrypt using DigitalOcean DNS validation.

### DigitalOcean DNS Validation

The ClusterIssuer is configured to use DigitalOcean DNS for domain validation, which allows for:
- Wildcard certificate support
- No need for HTTP-01 challenges
- Automatic domain validation via DNS records

### Configured Domains

The following domains are automatically configured with wildcard certificates:
- `*.alexmerenda.dev` and `alexmerenda.dev`
- `*.amer.dev` and `amer.dev`  
- `*.amerenda.dev` and `amerenda.dev`

### External Secret

The DigitalOcean API key is managed via External Secrets:
- **Secret Name**: `do-dns-api-key`
- **Source**: Bitwarden secret `do-dns-api-key`
- **Sync Wave**: 10 (high priority, after cert-manager bootstrap)

### Certificate Resources

Three Certificate resources are automatically created:
- `alexmerenda-dev-wildcard` → `alexmerenda-dev-wildcard-tls` secret
- `amer-dev-wildcard` → `amer-dev-wildcard-tls` secret
- `amerenda-dev-wildcard` → `amerenda-dev-wildcard-tls` secret

## Monitoring

cert-manager exposes metrics on port 9402 at the `/metrics` endpoint for Prometheus monitoring.
