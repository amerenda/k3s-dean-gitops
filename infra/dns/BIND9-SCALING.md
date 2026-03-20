# BIND9 Scaling Configuration

## Changes Made

### 1. Replica Scaling
- **Increased replicas**: From 1 to 3 replicas
- **Rolling update strategy**: Configured to allow rolling restarts without downtime
  - `maxUnavailable: 1` - Ensures at least 2 pods are always available during updates
  - `maxSurge: 1` - Allows 1 additional pod during updates

### 2. Pod Anti-Affinity
- **Host spreading**: Pods will be preferred to run on different nodes
- **Topology key**: `kubernetes.io/hostname` ensures distribution across hosts
- **Weight**: 100 (preferred, not required) - allows scheduling even if all nodes are full

### 3. Resource Management
- **CPU requests**: 50m (minimum guaranteed)
- **CPU limits**: 200m (maximum allowed)
- **Memory requests**: 128Mi (minimum guaranteed)
- **Memory limits**: 256Mi (maximum allowed)

### 4. Service Configuration
- **LoadBalancer**: Already configured with static IP `10.100.20.241`
- **Automatic load balancing**: Service will distribute traffic across all 3 replicas
- **No changes needed**: Service configuration is already optimal for multiple replicas

## Benefits

### High Availability
- **Fault tolerance**: DNS service continues even if 1-2 pods fail
- **Rolling updates**: Can update BIND9 without DNS downtime
- **Load distribution**: Traffic spread across multiple pods

### Performance
- **Reduced load per pod**: Each pod handles 1/3 of the DNS traffic
- **Better resource utilization**: Multiple smaller pods vs one large pod
- **Improved response times**: Load balancing across multiple instances

## Monitoring Commands

### Check Pod Distribution
```bash
# Verify pods are running on different nodes
kubectl get pods -n default -l app=bind9 -o wide

# Check pod anti-affinity is working
kubectl describe pods -n default -l app=bind9 | grep -A5 -B5 "Node-Selectors\|Tolerations"
```

### Monitor Rolling Updates
```bash
# Watch deployment status during updates
kubectl rollout status deployment/bind9 -n default

# Check deployment history
kubectl rollout history deployment/bind9 -n default
```

### Test DNS Resolution
```bash
# Test DNS resolution from different sources
nslookup home.amer.home 10.100.20.241
nslookup argocd.amer.home 10.100.20.241
nslookup longhorn.amer.home 10.100.20.241

# Test from within cluster
kubectl run test-dns --image=busybox --rm -it -- nslookup home.amer.home
```

### Check Resource Usage
```bash
# Monitor resource usage
kubectl top pods -n default -l app=bind9

# Check pod events
kubectl get events -n default --sort-by='.lastTimestamp' | grep bind9
```

## Troubleshooting

### If Pods Don't Distribute
```bash
# Check node capacity
kubectl describe nodes | grep -A5 "Allocated resources"

# Check if anti-affinity is working
kubectl get pods -n default -l app=bind9 -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.nodeName}{"\n"}{end}'
```

### If Rolling Updates Fail
```bash
# Check deployment status
kubectl describe deployment bind9 -n default

# Check pod logs
kubectl logs -n default -l app=bind9 --tail=50

# Force restart if needed
kubectl rollout restart deployment/bind9 -n default
```

## Expected Behavior

1. **Initial deployment**: 3 pods should start and distribute across available nodes
2. **Rolling updates**: When updating, only 1 pod will be unavailable at a time
3. **Load balancing**: DNS queries will be distributed across all 3 pods
4. **Fault tolerance**: If 1 pod fails, the other 2 continue serving DNS requests

## Rollback Plan

If issues occur, you can rollback:
```bash
# Rollback to previous version
kubectl rollout undo deployment/bind9 -n default

# Or scale back to 1 replica temporarily
kubectl scale deployment bind9 --replicas=1 -n default
```
