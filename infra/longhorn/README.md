# Longhorn Setup for k3s on Raspberry Pi

This directory contains the Longhorn distributed storage setup for your k3s cluster running on Raspberry Pi devices, deployed via GitOps using ArgoCD and Helm.

## Overview

Longhorn provides distributed block storage with built-in replication, making it perfect for resilient shared storage across your Raspberry Pi nodes. This setup includes automated backups to Google Cloud Storage.

## Features

- **Distributed Storage**: Data replicated across multiple nodes
- **High Availability**: Pods can be scheduled on any node
- **Snapshots**: Built-in backup capabilities
- **Automated Backups**: Daily backups to GCS at 2 AM
- **Web UI**: Easy management and monitoring
- **ARM64 Support**: Optimized for Raspberry Pi
- **GitOps Deployment**: Managed via ArgoCD

## Files

- `values.yaml`: Helm chart values for Longhorn configuration
- `longhorn-ui-lb.yaml`: LoadBalancer service for Longhorn UI
- `longhorn-config.yaml`: Longhorn configuration settings
- `backups/`: Backup configuration directory
  - `externalsecret.yaml`: GCS credentials from Bitwarden
  - `recurringjob.yaml`: Daily backup job configuration
- `README.md`: This documentation

## Deployment

Longhorn is deployed automatically via ArgoCD as part of the GitOps workflow:

1. **ArgoCD Application**: `infra-longhorn` manages the deployment
2. **Helm Chart**: Uses official Longhorn Helm chart v1.6.0
3. **Configuration**: Managed via `values.yaml`
4. **Backups**: Configured via ExternalSecrets and RecurringJobs

## Access the UI

- **LoadBalancer**: http://longhorn.amer.home (IP: 10.100.20.243)
- **Port-Forward (Alternative)**:
  ```bash
  kubectl port-forward -n default svc/longhorn-frontend 8080:80
  ```
  Then open http://localhost:8080 in your browser

## Storage Class Usage

Update your applications to use the `longhorn` storage class:
   ```yaml
   persistentVolumeClaim:
     enabled: true
     storageClass: longhorn
     accessModes: [ReadWriteMany]
     size: 1Gi
   ```

## Configuration

### Service Configuration

The Longhorn service configuration is critical for proper access to the UI. Here's the correct service block structure from the Helm chart:

```yaml
service:
  ui:
    # -- Service type for Longhorn UI. (Options: "ClusterIP", "NodePort", "LoadBalancer", "Rancher-Proxy")
    type: ClusterIP
    # -- NodePort port number for Longhorn UI. When unspecified, Longhorn selects a free port between 30000 and 32767.
    nodePort: null
    # -- Annotation for the Longhorn UI service.
    annotations: {}
    ## If you want to set annotations for the Longhorn UI service, delete the `{}` in the line above
    ## and uncomment this example block
    #  annotation-key1: "annotation-value1"
    #  annotation-key2: "annotation-value2"
  manager:
    # -- Service type for Longhorn Manager.
    type: ClusterIP
    # -- NodePort port number for Longhorn Manager. When unspecified, Longhorn selects a free port between 30000 and 32767.
    nodePort: ""
```

**Important Notes:**
- The default `type` should be `ClusterIP` for both UI and Manager services
- For external access, use a separate LoadBalancer service or port-forward
- Do not change the service type to LoadBalancer in the main values.yaml as this can cause issues

### Storage Class Settings

- **Default Replica Count**: 2 (data replicated across 2 nodes)
- **Access Mode**: ReadWriteMany (pods can be scheduled anywhere)
- **Reclaim Policy**: Delete (volumes deleted when PVC is deleted)

### Resource Limits

Optimized for Raspberry Pi with limited resources:
- **Manager**: 100m CPU, 128Mi memory
- **UI**: 50m CPU, 64Mi memory
- **Engine**: 50m CPU, 64Mi memory

### Backup Configuration

- **Backup Target**: GCS bucket `amerenda-backups` with path `k3s/dean`
- **Credentials**: Managed via ExternalSecrets from Bitwarden
- **Schedule**: Daily backups at 2:00 AM
- **Retention**: Managed by GCS lifecycle policies
- **Endpoint**: Google Cloud Storage S3-compatible API

## Usage Examples

### Pi-hole with Longhorn

Update your Pi-hole values.yaml:
```yaml
persistentVolumeClaim:
  enabled: true
  storageClass: longhorn
  accessModes: [ReadWriteMany]
  size: 1Gi
```

### Home Assistant with Longhorn

```yaml
persistence:
  enabled: true
  storageClass: longhorn
  accessModes: [ReadWriteMany]
  size: 8Gi
```

## Monitoring

### Check Longhorn Status
```bash
kubectl get pods -n default -l app.kubernetes.io/name=longhorn
kubectl get storageclass
kubectl get pv
kubectl get recurringjobs
```

### View Longhorn Logs
```bash
kubectl logs -n default -l app.kubernetes.io/name=longhorn-manager
kubectl logs -n default -l app.kubernetes.io/name=longhorn-ui
```

### Check Backup Status
```bash
kubectl get externalsecret gcs-backup-credentials -n default
kubectl get recurringjob daily-backup-2am -n default
```

## Troubleshooting

### Common Issues

1. **Pods not starting**: Check if Longhorn is ready
   ```bash
   kubectl get pods -n default -l app.kubernetes.io/name=longhorn
   ```

2. **Storage not available**: Verify storage class
   ```bash
   kubectl get storageclass
   ```

3. **Replication issues**: Check node status in Longhorn UI

4. **Backup issues**: Check ExternalSecret and RecurringJob status
   ```bash
   kubectl get externalsecret gcs-backup-credentials -n default
   kubectl get recurringjob daily-backup-2am -n default
   kubectl describe externalsecret gcs-backup-credentials -n default
   ```

### GitOps Management

- **Configuration**: Edit `values.yaml` and commit changes
- **Backup Settings**: Modify files in `backups/` directory
- **ArgoCD Sync**: Changes are automatically applied via ArgoCD
- **Manual Sync**: Use ArgoCD UI to force sync if needed

## Benefits for Your Setup

- **Pod Mobility**: Pi-hole and other services can run on any node
- **Data Resilience**: 2 replicas across different SD cards
- **Easy Migration**: Simple to move from local-path to Longhorn
- **Backup Ready**: Built-in snapshot capabilities
- **Resource Efficient**: Designed for edge computing

## Next Steps

1. **Verify Deployment**: Check ArgoCD application `infra-longhorn` is synced
2. **Test Storage**: Create a test PVC using the `longhorn` storage class
3. **Configure Backups**: Ensure GCS credentials are in Bitwarden
4. **Monitor Backups**: Check RecurringJob status and backup logs
5. **Migrate Applications**: Update existing PVCs to use Longhorn storage class