# Monitoring Stack

Cluster monitoring uses [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack) (v82.1.0). Prometheus runs in full mode (not Agent mode) so it can evaluate rules locally, and is intentionally a thin ephemeral edge buffer — see the storage/resources comments in `values.yaml`.

## Components

- **Prometheus** -- scrapes cluster and external targets, evaluates alerting rules locally, and forwards samples via `remote_write` to primary Prometheus on mac-mini.
- **Alertmanager** -- fires alerts from local rule evaluation to Pushover (see `alerting/`).
- **node-exporter** -- host-level metrics (CPU, memory, disk, network) per node.
- **kube-state-metrics** -- Kubernetes object metrics (pods, deployments, nodes).
- **Prometheus Operator** -- manages `Prometheus`, `Alertmanager`, `AlertmanagerConfig`, `ServiceMonitor`, and `PodMonitor` CRDs.

Grafana is no longer deployed in this namespace. It runs on mac-mini and is exposed at `https://grafana.amer.dev` through `infra/ingresses/grafana-mini-ingress-amer-dev.yaml`.

## Alerting

`alerting/` holds an `ExternalSecret` (pulls `pushover-user-key` / `pushover-alerts-api-key` from BWS into the `pushover-credentials` Secret) and an `AlertmanagerConfig` that routes alerts to Pushover. The Alertmanager CR's `alertmanagerConfigSelector`/`alertmanagerConfigNamespaceSelector` are both `{}` (match everything), so any `AlertmanagerConfig` in any namespace is auto-discovered — no label needed.

## Data Flow

```
k3s targets (ServiceMonitors/PodMonitors/static jobs)
  -> Prometheus Agent in monitoring namespace
  -> remote_write to mac-mini Prometheus (10.100.20.18:9090)
  -> Grafana on mac-mini
```

## Validation

- Check Agent targets:
  ```bash
  kubectl get pods -n monitoring -l app.kubernetes.io/name=prometheus
  kubectl port-forward -n monitoring svc/prometheus-operated 9091:9090
  ```
  Then open `http://localhost:9091/targets`.
- Check remote write health:
  ```bash
  kubectl port-forward -n monitoring svc/prometheus-operated 9091:9090
  ```
  Query:
  - `prometheus_remote_storage_samples_pending`
  - `prometheus_remote_storage_failed_samples_total`
