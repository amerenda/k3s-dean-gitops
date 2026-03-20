# Grafana dashboards (Infra & Apps)

ConfigMaps in this directory are applied to the `monitoring` namespace and picked up by the Grafana dashboard sidecar (label `grafana_dashboard: "1"`). They appear in Grafana under folders **Infra** and **Apps**.

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
| **App: Pi-hole** | 10176 (Pi-hole Exporter – requires Prometheus + pihole-exporter) |

Datasource variable `DS_PROMETHEUS` is set to the default Prometheus datasource (`prometheus`) for provisioning.

## Placeholder dashboards

The remaining infra/app dashboards (Flannel, DNS/BIND9, External DNS, Tailscale, MetalLB, Reloader, ARC, Home Assistant, UniFi, etc.) are minimal placeholders. To use a full dashboard for those, go to Grafana → Dashboards → New → Import and search by name or ID on [grafana.com/grafana/dashboards](https://grafana.com/grafana/dashboards/).
