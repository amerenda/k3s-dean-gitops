# External Secrets Operator with cert-manager Integration

This directory contains the Helm chart configuration for External Secrets Operator with cert-manager integration for secure TLS communication.

## Overview

External Secrets Operator integrates with cert-manager to provide secure, encrypted communication for secret management. This setup includes:

- **cert-manager Integration**: Automatic TLS certificate management
- **Let's Encrypt Issuers**: Both production and staging ClusterIssuers
- **Webhook Certificates**: Secure communication for external-secrets webhook
- **Bitwarden SecretStore**: TLS-enabled connection to Bitwarden

## Components

### 1. ClusterIssuers
- **letsencrypt-prod**: Production Let's Encrypt issuer for live certificates
- **letsencrypt-staging**: Staging Let's Encrypt issuer for testing

### 2. Webhook Certificate
- **external-secrets-webhook-cert**: TLS certificate for the external-secrets webhook
- Automatically managed by cert-manager
- Includes all necessary DNS names for cluster communication

### 3. Bitwarden SecretStore
- **bitwarden-secretstore**: TLS-enabled SecretStore for Bitwarden integration
- Uses webhook provider with TLS certificates
- Secure communication with Bitwarden SDK Server

## Configuration

The configuration is defined in `values.yaml` and includes:

- **cert-manager Integration**: `certManager.enabled: true`
- **Webhook Configuration**: Secure port 9443 with TLS
- **Security Contexts**: Non-root user with proper permissions
- **Resource Limits**: Appropriate CPU and memory allocation

## Usage

### Creating Certificates

You can create certificates for your applications using the ClusterIssuers:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: my-app-cert
  namespace: my-namespace
spec:
  secretName: my-app-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
  - my-app.example.com
```

### Using External Secrets

Create ExternalSecret resources to sync secrets from Bitwarden:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: my-secret
  namespace: my-namespace
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: bitwarden-secretstore
    kind: SecretStore
  target:
    name: my-secret
    creationPolicy: Owner
  data:
  - secretKey: password
    remoteRef:
      key: my-password
      property: password
```

## Security Features

- **TLS Encryption**: All webhook communication is encrypted
- **Certificate Management**: Automatic certificate renewal via cert-manager
- **Secure Communication**: Bitwarden integration uses TLS certificates
- **RBAC**: Proper role-based access control
- **Non-root Execution**: All containers run as non-root user

## Monitoring

External Secrets Operator exposes metrics and health checks for monitoring integration with Prometheus and other monitoring solutions.

## Dependencies

- cert-manager v1.19.0+
- Kubernetes cluster with RBAC enabled
- Bitwarden SDK Server
- ArgoCD for GitOps deployment