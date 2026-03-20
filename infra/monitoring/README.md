# Monitoring Stack

Cluster monitoring via [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack) (v82.1.0).

## Components

- **Prometheus** -- metrics collection and storage (7-day retention, 10Gi Longhorn PVC)
- **Grafana** -- dashboards and visualization at `http://grafana.amer.home` (includes per-infra and per-app placeholder dashboards under folders **Infra** and **Apps**)
- **node-exporter** -- host-level metrics (CPU, memory, disk, network) per node (kubelet scrape disabled on K3s; use this for node metrics)
- **kube-state-metrics** -- Kubernetes object metrics (pods, deployments, nodes)
- **Prometheus Operator** -- manages Prometheus and ServiceMonitor CRDs

AlertManager is disabled.

## Access

| Service | Address |
|---------|---------|
| Grafana | `https://grafana.amer.home` (via Traefik Ingress, TLS) |
| Prometheus | ClusterIP only (internal) |

Grafana uses a **Recreate** deployment strategy (not RollingUpdate) so only one pod uses the RWO PVC at a time, avoiding “Multi-Attach” errors. If a rollout is stuck with that error, delete the old Grafana pod so the new one can attach the volume.

Grafana’s Prometheus datasource is set to `http://infra-monitoring-kube-prom-prometheus:9090` (Prometheus service in same namespace). If dashboards show no data, check in Grafana: Configuration → Data sources → Prometheus that the URL is correct and “Save & test” succeeds.

**No metrics in dashboards (datasource OK):** Prometheus may have data only up to an older time (e.g. after a crash or TSDB corruption). In Grafana, set the dashboard time range to “Last 7 days” or pick a range that includes when data was last scraped. To confirm: port-forward Prometheus and open `http://localhost:9090/query`, run `up` — if empty, try `up` with a time a few hours ago. If the API shows `corruptionCount: 1` under Status → Runtime & Build Information, consider wiping Prometheus storage so it can re-scrape from scratch: delete the Prometheus PVC in the `monitoring` namespace (or scale the StatefulSet to 0, delete the PVC, scale back to 1). You will lose history but new scrapes will store correctly.

### Grafana login

- **Username:** `admin`
- **Password:** If you previously reset it via the CLI, use that password. Otherwise decode from the cluster secret:
  ```bash
  kubectl get secret infra-monitoring-grafana -n monitoring -o jsonpath='{.data.admin-password}' | base64 -d
  ```
  (No trailing newline; copy the output as the password.)

`root_url` and `domain` are set so that browser login at `https://grafana.amer.home` works (cookies and redirects). After changing values, sync/restart Grafana so the new config is applied.

If login still fails, Grafana only applies the secret password when it first creates the admin user. If the secret was changed after the initial deploy (e.g. by Helm), the running instance may still use the original password. Reset it via the Grafana CLI in the pod:
  ```bash
  kubectl exec -n monitoring deploy/infra-monitoring-grafana -- grafana cli admin reset-admin-password NEW_PASSWORD
  ```
  Then log in with `admin` and the new password.
