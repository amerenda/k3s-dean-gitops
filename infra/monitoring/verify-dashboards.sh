#!/bin/bash
# Verify all Grafana dashboard metrics exist in Prometheus
# Usage: ./verify-dashboards.sh
# Requires: kubectl with access to the cluster, port-forward to prometheus
#
# This script port-forwards to Prometheus, then checks every metric
# referenced in every dashboard. Reports missing metrics per dashboard.

set -euo pipefail

PROM_PORT=19090
PROM_NS="monitoring"
PROM_SVC="svc/infra-monitoring-kube-prom-prometheus"
PASS=0
FAIL=0
WARN=0

cleanup() {
  if [[ -n "${PF_PID:-}" ]]; then
    kill "$PF_PID" 2>/dev/null || true
    wait "$PF_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "=== Prometheus Dashboard Metric Verifier ==="
echo ""

# Kill any leftover port-forwards on our port
fuser -k "${PROM_PORT}/tcp" 2>/dev/null || true
sleep 1

# Start port-forward
echo "Starting port-forward to Prometheus..."
kubectl port-forward -n "$PROM_NS" "$PROM_SVC" "${PROM_PORT}:9090" &>/dev/null &
PF_PID=$!

# Wait for port-forward to be ready (retry up to 15 seconds)
PROM_URL="http://localhost:${PROM_PORT}"
for i in $(seq 1 15); do
  if curl -sf "${PROM_URL}/api/v1/status/runtimeinfo" &>/dev/null; then
    break
  fi
  if ! kill -0 "$PF_PID" 2>/dev/null; then
    echo "ERROR: Port-forward failed. Is the cluster reachable?"
    exit 1
  fi
  sleep 1
done

if ! curl -sf "${PROM_URL}/api/v1/status/runtimeinfo" &>/dev/null; then
  echo "ERROR: Prometheus not responding after 15s"
  exit 1
fi

# Helper: check if a metric exists in Prometheus
check_metric() {
  local metric="$1"
  local result
  result=$(curl -sf "${PROM_URL}/api/v1/label/__name__/values" 2>/dev/null | grep -c "\"${metric}\"" || true)
  [[ "$result" -gt 0 ]]
}

# Helper: check a dashboard
check_dashboard() {
  local name="$1"
  shift
  local metrics=("$@")
  local missing=()

  for m in "${metrics[@]}"; do
    if ! check_metric "$m"; then
      missing+=("$m")
    fi
  done

  if [[ ${#missing[@]} -eq 0 ]]; then
    echo "  ✅ ${name} — all ${#metrics[@]} metrics present"
    PASS=$((PASS + 1))
  else
    echo "  ❌ ${name} — ${#missing[@]}/${#metrics[@]} metrics MISSING:"
    for m in "${missing[@]}"; do
      echo "       - $m"
    done
    FAIL=$((FAIL + 1))
  fi
}

# Fetch all metric names once to a temp file (avoids bash variable truncation)
METRICS_FILE=$(mktemp)
trap 'cleanup; rm -f "$METRICS_FILE"' EXIT

echo "Fetching metric inventory from Prometheus..."
curl -sf --max-time 30 "${PROM_URL}/api/v1/label/__name__/values" \
  | python3 -c "import sys,json; print('\n'.join(json.load(sys.stdin)['data']))" \
  > "$METRICS_FILE" 2>/dev/null

METRIC_COUNT=$(wc -l < "$METRICS_FILE")
if [[ "$METRIC_COUNT" -lt 10 ]]; then
  echo "ERROR: Could not fetch metrics from Prometheus at ${PROM_URL} (got ${METRIC_COUNT} metrics)"
  exit 1
fi

echo "Found ${METRIC_COUNT} unique metrics in Prometheus."
echo ""

# Override check_metric to use the temp file
check_metric() {
  grep -qx "$1" "$METRICS_FILE"
}

echo "--- INFRASTRUCTURE DASHBOARDS ---"
echo ""

check_dashboard "Infra: Node Exporter" \
  node_cpu_seconds_total node_load1 node_load5 node_load15 \
  node_memory_MemTotal_bytes node_memory_MemAvailable_bytes \
  node_memory_Cached_bytes node_memory_Buffers_bytes \
  node_filesystem_avail_bytes node_filesystem_size_bytes \
  node_disk_read_bytes_total node_disk_written_bytes_total \
  node_network_receive_bytes_total node_network_transmit_bytes_total \
  node_network_receive_errs_total node_network_transmit_errs_total

check_dashboard "Infra: Kubernetes Cluster" \
  kube_node_info kube_node_status_condition kube_namespace_created \
  kube_pod_status_phase kube_deployment_created kube_service_info \
  node_cpu_seconds_total node_memory_MemAvailable_bytes node_memory_MemTotal_bytes \
  kube_pod_container_status_restarts_total kube_deployment_spec_replicas \
  kube_deployment_status_replicas_available kube_deployment_status_replicas_unavailable \
  container_cpu_usage_seconds_total container_memory_working_set_bytes \
  machine_cpu_cores node_network_receive_bytes_total node_network_transmit_bytes_total \
  apiserver_request_total apiserver_request_duration_seconds_bucket up

check_dashboard "Infra: Monitoring (Prometheus)" \
  process_start_time_seconds up prometheus_tsdb_head_series \
  prometheus_tsdb_storage_blocks_bytes prometheus_target_scrape_pools_failed_total \
  prometheus_tsdb_head_samples_appended_total prometheus_target_interval_length_seconds \
  prometheus_engine_query_duration_histogram_seconds_bucket prometheus_tsdb_compactions_total \
  prometheus_tsdb_compactions_failed_total prometheus_tsdb_wal_storage_size_bytes \
  prometheus_tsdb_checkpoint_creations_total container_cpu_usage_seconds_total \
  container_memory_working_set_bytes kube_pod_container_resource_limits

check_dashboard "Infra: Longhorn" \
  longhorn_volume_capacity_bytes longhorn_volume_robustness \
  longhorn_volume_actual_size_bytes longhorn_volume_state \
  longhorn_node_count_total longhorn_node_status \
  longhorn_node_storage_usage_bytes longhorn_node_storage_capacity_bytes \
  longhorn_disk_usage_bytes longhorn_disk_capacity_bytes

check_dashboard "Infra: Traefik" \
  traefik_config_reloads_total traefik_entrypoint_requests_total \
  traefik_entrypoint_request_duration_seconds_bucket \
  traefik_service_requests_total traefik_service_request_duration_seconds_sum \
  traefik_service_request_duration_seconds_count traefik_service_requests_bytes_total \
  traefik_open_connections

check_dashboard "Infra: MetalLB" \
  metallb_allocator_addresses_total metallb_allocator_addresses_in_use_total \
  kube_service_spec_type metallb_layer2_requests_received metallb_layer2_responses_sent

check_dashboard "Infra: cert-manager" \
  certmanager_certificate_ready_status certmanager_certificate_expiration_timestamp_seconds \
  certmanager_certificate_renewal_timestamp_seconds certmanager_http_acme_client_request_count

check_dashboard "Infra: cert-manager (external)" \
  certmanager_certificate_ready_status certmanager_certificate_expiration_timestamp_seconds \
  certmanager_certificate_renewal_timestamp_seconds

check_dashboard "Infra: External Secrets" \
  controller_runtime_active_workers controller_runtime_max_concurrent_reconciles \
  controller_runtime_reconcile_total controller_runtime_reconcile_errors_total \
  controller_runtime_reconcile_time_seconds_bucket workqueue_depth workqueue_adds_total \
  externalsecret_sync_calls_total externalsecret_sync_calls_error \
  externalsecret_status_condition

check_dashboard "Infra: CoreDNS" \
  coredns_dns_request_duration_seconds_bucket coredns_dns_requests_total \
  coredns_cache_entries coredns_cache_hits_total coredns_cache_misses_total \
  coredns_dns_responses_total

check_dashboard "Infra: External DNS" \
  external_dns_source_endpoints_total external_dns_registry_endpoints_total \
  external_dns_registry_errors_total external_dns_controller_verified_records

check_dashboard "Infra: DNS (BIND9) — pod health only" \
  kube_pod_status_phase kube_pod_container_status_restarts_total \
  kube_pod_container_status_ready container_cpu_usage_seconds_total \
  container_memory_working_set_bytes container_network_receive_bytes_total \
  container_network_transmit_bytes_total container_fs_writes_bytes_total \
  container_fs_reads_bytes_total

check_dashboard "Infra: Flannel" \
  container_network_receive_bytes_total container_network_transmit_bytes_total \
  container_network_receive_errors_total container_network_transmit_errors_total \
  container_cpu_usage_seconds_total container_memory_working_set_bytes

check_dashboard "Infra: Tailscale" \
  kube_pod_status_phase kube_pod_container_status_restarts_total \
  container_network_receive_bytes_total container_network_transmit_bytes_total \
  container_cpu_usage_seconds_total container_memory_working_set_bytes

check_dashboard "Infra: ARC Controller" \
  kube_pod_status_phase kube_pod_container_status_restarts_total \
  container_cpu_usage_seconds_total container_memory_working_set_bytes \
  controller_runtime_reconcile_total controller_runtime_reconcile_time_seconds_bucket \
  workqueue_queue_duration_seconds_bucket

check_dashboard "Infra: ARC Runners" \
  kube_pod_status_phase container_cpu_usage_seconds_total \
  container_memory_working_set_bytes container_network_receive_bytes_total \
  container_network_transmit_bytes_total

check_dashboard "Infra: Reloader" \
  kube_pod_status_phase kube_pod_container_status_restarts_total \
  reloader_reloads_total reloader_watches \
  container_cpu_usage_seconds_total container_memory_working_set_bytes

echo ""
echo "--- APPLICATION DASHBOARDS ---"
echo ""

check_dashboard "App: Pi-hole" \
  pihole_status pihole_domains_being_blocked pihole_unique_domains \
  pihole_dns_queries_all_types pihole_ads_blocked_today \
  pihole_ads_percentage_today pihole_queries_cached pihole_queries_forwarded

check_dashboard "App: Ecdysis" \
  moltbook_backend_agents_running process_start_time_seconds \
  process_resident_memory_bytes python_gc_collections_total \
  process_open_fds process_cpu_seconds_total kube_pod_status_phase \
  kube_pod_container_status_restarts_total

check_dashboard "App: LLM Manager" \
  llm_backend_registered_apps llm_backend_api_requests_total \
  moltbook_backend_agents_running

check_dashboard "App: UniFi Network Application" \
  kube_pod_status_phase kube_pod_start_time kube_pod_container_status_restarts_total \
  container_cpu_usage_seconds_total container_memory_working_set_bytes \
  container_network_receive_bytes_total container_network_transmit_bytes_total \
  kubelet_volume_stats_used_bytes kubelet_volume_stats_capacity_bytes

echo ""
echo "--- CI DASHBOARDS ---"
echo ""

check_dashboard "CI: Builds In Flight" \
  kube_pod_status_phase kube_pod_created kube_pod_container_resource_requests \
  kube_pod_info kube_pod_start_time kube_pod_container_status_restarts_total

echo ""
echo "=========================================="
echo "  RESULTS: ✅ ${PASS} passed | ❌ ${FAIL} failed"
echo "=========================================="
echo ""

if [[ $FAIL -gt 0 ]]; then
  echo "Some dashboards have missing metrics. Check:"
  echo "  1. Prometheus targets: ${PROM_URL}/targets"
  echo "  2. ServiceMonitor status: kubectl get servicemonitor -A"
  echo "  3. PodMonitor status: kubectl get podmonitor -A"
  exit 1
else
  echo "All dashboard metrics verified! 🎉"
fi
