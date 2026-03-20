# DNS Optimization Changes

## Problem
External-dns was making frequent updates to BIND9, causing DNS lag and excessive logging. The logs showed external-dns was constantly trying to recreate DNS records that already existed.

## Root Causes
1. **Debug logging**: External-dns was running with debug log level, creating excessive log output
2. **No sync interval**: External-dns was checking for changes very frequently (default behavior)
3. **Low TTL values**: DNS records had 300-second TTL, causing frequent DNS queries
4. **Missing optimization settings**: No interval controls or event filtering

## Changes Made

### 1. External-DNS Configuration (`values.yaml`)
- **Added sync intervals**: `--interval=1m` and `--sync-interval=1m` to limit update frequency
- **Reduced log level**: Changed from `debug` to `info` to reduce log noise
- **Added registry settings**: `--registry=txt` and `--txt-owner-id=external-dns` for better record management
- **Added event filtering**: `minEventSyncInterval: 1m` to reduce event processing

### 2. BIND9 Zone Files (`configmap.yaml`)
- **Increased TTL**: Changed from 300 seconds (5 minutes) to 3600 seconds (1 hour)
- **Applied to all zones**: `merenda.home.arpa`, `amer.home`, and `20.100.10.in-addr.arpa`

### 3. Service Annotations
- **Updated TTL**: Changed service TTL from 300 to 3600 seconds to match zone TTL

## Expected Results
- **Reduced DNS updates**: External-dns will only sync every minute instead of continuously
- **Less log noise**: Info-level logging will show only important events
- **Better DNS performance**: Higher TTL values will reduce DNS query frequency
- **Reduced BIND9 load**: Fewer unnecessary DNS record updates

## Monitoring
To verify the changes are working:

```bash
# Check external-dns logs (should be much quieter)
kubectl logs -n default -l app.kubernetes.io/name=external-dns --tail=20

# Check BIND9 logs (should show fewer updates)
kubectl logs -n default deployment/bind9 --tail=20

# Test DNS resolution
nslookup home.amer.home
nslookup argocd.amer.home
```

## Additional Recommendations

### 1. Consider Reducing Hostname Annotations
Some services have multiple hostnames (e.g., home-assistant has 3 hostnames). Consider if all are necessary:
- `home.amer.home,ha.amer.home,homeassistant.amer.home` → Could be reduced to just `home.amer.home`

### 2. Monitor Resource Usage
- Check if external-dns CPU/memory usage decreases
- Monitor BIND9 performance improvements

### 3. Consider Further Optimizations
- If still experiencing issues, consider increasing sync interval to 2-5 minutes
- Add `--dry-run=true` temporarily to test changes without applying them
- Consider using `--ignore-hostname-annotation` if some services don't need DNS management

## Rollback Plan
If issues occur, revert changes:
1. Revert `values.yaml` to original settings
2. Revert `configmap.yaml` TTL values to 300
3. Revert service TTL annotations to 300
4. Restart external-dns and BIND9 pods
