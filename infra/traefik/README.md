# Traefik Ingress Controller

This directory contains the configuration for Traefik ingress controller, optimized for k3s on Raspberry Pi.

## Overview

Traefik is configured to:
- Provide ingress controller functionality for k3s
- Enable automatic service discovery
- Support both HTTP and HTTPS with Let's Encrypt
- Optimize resource usage for Raspberry Pi
- Integrate with external-dns for automatic DNS management

## Configuration

### Features Enabled
- **Dashboard**: Accessible at `traefik.amer.home`
- **Metrics**: Prometheus metrics enabled
- **ACME**: Let's Encrypt certificate management
- **Cross-namespace**: Support for services across namespaces
- **External services**: Support for ExternalName services

### Resource Limits
- **CPU**: 100m request, 200m limit
- **Memory**: 64Mi request, 128Mi limit
- **Storage**: 1Gi persistent volume for certificates

### Security
- Non-root user execution
- Read-only root filesystem where possible
- Proper capability dropping

## Deployment

Traefik is deployed via ArgoCD as part of the root application:
- **Chart**: Traefik Helm Chart
- **Namespace**: `default` (required)
- **Values**: `gitops/infra/traefik/values.yaml`

## Usage

### Creating Ingress Resources

For services using hostNetwork, create an ingress resource:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: homeassistant-ingress
  namespace: home-assistant
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web,websecure
    traefik.ingress.kubernetes.io/router.tls: "true"
    external-dns.alpha.kubernetes.io/hostname: home.amer.home,ha.amer.home
    external-dns.alpha.kubernetes.io/ttl: "3600"
spec:
  ingressClassName: traefik
  rules:
  - host: home.amer.home
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: homeassistant
            port:
              number: 8123
```

### Dashboard Access

The Traefik dashboard is available at:
- **URL**: `https://traefik.amer.home`
- **Authentication**: None (internal network only)

## Integration with External-DNS

Traefik works with external-dns to automatically manage DNS records:
- Ingress resources with `external-dns.alpha.kubernetes.io/hostname` annotations
- Automatic A record creation for ingress hosts
- TTL management for DNS records

## Troubleshooting

### Check Traefik Status
```bash
kubectl get pods -n default -l app.kubernetes.io/name=traefik
```

### View Traefik Logs
```bash
kubectl logs -n default -l app.kubernetes.io/name=traefik
```

### Check Ingress Resources
```bash
kubectl get ingress --all-namespaces
```

### Test Dashboard
```bash
curl -k https://traefik.amer.home/dashboard/
```

## Security Notes

- Dashboard is exposed without authentication (internal network only)
- ACME certificates are stored in persistent volume
- Cross-namespace access is enabled for flexibility
- External services are supported for complex routing
