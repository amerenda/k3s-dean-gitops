# Grafana dashboards (Infra & Apps)

ConfigMaps in this directory are applied to the `monitoring` namespace. Grafana on mac-mini (`mac-mini-compose`) mirrors these dashboards via file provisioning using `scripts/extract-grafana-dashboards-from-gitops.py` (same JSON payloads, folders from the `grafana_folder` annotation).

## Full dashboards (imported from Grafana.com)

| Dashboard | Source (Grafana.com ID) |
|-----------|--------------------------|
| **Infra: Longhorn** | 16888 |
| **Infra: Traefik** | 17347 (Traefik Official Kubernetes) |
| **Infra: cert-manager** | 20842 |
| **Infra: External Secrets** | 21640 |
| **Infra: CoreDNS** | 12382 (K8S CoreDNS) |
| **Infra: Node Exporter** | 1860 (Node Exporter Full) |
| **Infra: Kubernetes Cluster** | 15757 |

Datasource variable `DS_PROMETHEUS` is set to the default Prometheus datasource (`prometheus`) for provisioning.

## Placeholder dashboards

The remaining infra/app dashboards (Flannel, DNS/BIND9, External DNS, Tailscale, MetalLB, Reloader, ARC, Home Assistant, UniFi, etc.) are minimal placeholders. To use a full dashboard for those, go to Grafana → Dashboards → New → Import and search by name or ID on [grafana.com/grafana/dashboards](https://grafana.com/grafana/dashboards/).
