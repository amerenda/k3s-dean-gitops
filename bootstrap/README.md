# Bootstrap Configuration

This directory contains initial configuration files required to bootstrap the k3s cluster and GitOps workflow.

## 📁 Contents

### `argocd/values.yaml`
ArgoCD Helm chart values for the initial installation:
- **LoadBalancer Service**: Exposes ArgoCD UI via MetalLB
- **External DNS**: Configures hostname `argocd.amer.home`
- **Security**: Disables TLS for local network access
- **Configuration**: Sets up URL and instance labeling

### `bitwarden-credentials-secret.yaml`
Kubernetes Secret template for Bitwarden integration:
- **Access Token**: Placeholder for your Bitwarden access token
- **External Secrets**: Required for fetching secrets from Bitwarden
- **Security**: Must be applied manually for security

### `appprojects.yaml`
ArgoCD AppProject resources defining project permissions:
- **infra Project**: For infrastructure components (storage, networking, DNS, etc.)
- **application Project**: For application deployments (Home Assistant, Pi-hole, etc.)
- **Permissions**: Configured to allow all repositories, namespaces, and resources
- **Required**: Must be applied before applications using these projects can sync

## 🚀 Usage

### 1. ArgoCD Installation
The ArgoCD values are automatically used during cluster setup:
```bash
# This happens automatically during ansible setup
ansible-playbook -i inventory.ini setup-k3s-cluster.yml -e k3s_token=$K3S_TOKEN
```

### 2. ArgoCD Projects Setup
**IMPORTANT**: These must be created before applications using project references can sync:

1. **Apply AppProjects**:
   ```bash
   kubectl apply -f bootstrap/appprojects.yaml
   ```

2. **Verify Projects**:
   ```bash
   kubectl get appproject
   ```
   
   You should see:
   - `default` (built-in)
   - `infra` (for infrastructure)
   - `application` (for applications)

3. **Check Project Details** (optional):
   ```bash
   kubectl describe appproject infra
   kubectl describe appproject application
   ```

**Note**: These projects define which repositories, namespaces, and resources ArgoCD applications can use. Both `infra` and `application` projects are configured with permissive settings (`*` for all) to allow flexibility.

### 3. Bitwarden Secret Setup
**IMPORTANT**: This must be done manually after cluster setup:

1. **Get Bitwarden Access Token**:
   - Go to [Bitwarden Vault](https://vault.bitwarden.com/#/sm/a9b83b36-d37e-4532-88a4-b36f00df7f3d/projects/6353f589-39c0-45f2-9e9c-b36f00e0c282/secrets)
   - Create a new access token
   - Copy the token value

2. **Update Secret File**:
   ```bash
   vim bootstrap/bitwarden-credentials-secret.yaml
   # Replace 'token_here' with your actual Bitwarden access token
   ```

3. **Apply Secret**:
   ```bash
   kubectl apply -f bootstrap/bitwarden-credentials-secret.yaml
   ```

4. **Verify Secret**:
   ```bash
   kubectl get secret bitwarden-credentials -n default
   kubectl describe secret bitwarden-credentials -n default
   ```

## 🔐 Security Notes

- **Never commit real tokens**: The `bitwarden-credentials-secret.yaml` contains placeholder values
- **Access token permissions**: Ensure your Bitwarden access token has appropriate permissions
- **Secret rotation**: Regularly rotate your Bitwarden access token
- **RBAC**: The secret is created in the `default` namespace with appropriate permissions

## 🔧 Customization

### ArgoCD Configuration
Edit `argocd/values.yaml` to customize:
- **Hostname**: Change `argocd.amer.home` to your domain
- **LoadBalancer IP**: Set specific IP for MetalLB
- **TLS**: Enable/disable TLS based on your needs
- **Resources**: Adjust CPU/memory limits

### ArgoCD Projects
Edit `appprojects.yaml` to customize project permissions:
- **Source Repositories**: Restrict which Git repos can be used (currently `*` allows all)
- **Destinations**: Restrict which namespaces/clusters apps can deploy to (currently `*` allows all)
- **Resource Whitelist**: Control which Kubernetes resources can be created (currently `*` allows all)
- **RBAC**: For stricter security, replace `*` with specific values per project

### Bitwarden Integration
The secret enables External Secrets Operator to fetch:
- **Tailscale Auth Keys**: For VPN authentication
- **GCS Backup Credentials**: For Longhorn backups
- **DNS TSIG Keys**: For BIND9 dynamic updates
- **Other Application Secrets**: As needed by your applications

## 🆘 Troubleshooting

### ArgoCD Not Accessible
```bash
# Check ArgoCD service
kubectl get svc argocd-server

# Check MetalLB
kubectl get svc -n metallb-system

# Port forward as fallback
kubectl port-forward svc/argocd-server 8080:80
```

### Applications Failing to Sync (Project Issues)
If applications are failing with project-related errors:
```bash
# Check if projects exist
kubectl get appproject

# Verify project permissions
kubectl describe appproject infra
kubectl describe appproject application

# Re-apply projects if needed
kubectl apply -f bootstrap/appprojects.yaml

# Check application status
kubectl get application -A
kubectl describe application <app-name> -n default
```

### Bitwarden Secret Issues
```bash
# Check secret exists
kubectl get secret bitwarden-credentials -n default

# Check External Secrets Operator
kubectl get pods -l app.kubernetes.io/name=external-secrets

# Check ExternalSecret resources
kubectl get externalsecrets -A
```

### External Secrets Not Working
```bash
# Check ClusterSecretStore
kubectl get clustersecretstore bitwarden-secretstore

# Check ExternalSecret status
kubectl describe externalsecret <secret-name>
```

## 📚 Next Steps

After bootstrap setup:
1. **Apply AppProjects**: Run `kubectl apply -f bootstrap/appprojects.yaml` if not already done
2. **Access ArgoCD**: Navigate to `http://argocd.amer.home` or port-forward
3. **Verify Applications**: Check that all applications are syncing (some reference `infra` or `application` projects)
4. **Monitor Secrets**: Ensure External Secrets are working correctly
5. **Configure Applications**: Customize application configurations as needed
