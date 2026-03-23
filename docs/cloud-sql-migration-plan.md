# Cloud SQL Migration Plan

## Overview

Migrate llm-manager and ecdysis from local Postgres to GCP Cloud SQL.
Each app gets its own database on a shared Cloud SQL instance (private IP only).

**Instance**: `dean-postgres` in project `amerenda-k3s`, region `us-east1`.
See [cloud-sql-bootstrap.md](cloud-sql-bootstrap.md) for provisioning commands.

## Current State

- **Single Postgres** in `llm-manager` namespace on murderbot
- **Shared database**: `llmmanager` with both LLM and ecdysis tables
- **Connection**: `postgresql://llm:PASSWORD@postgres.llm-manager.svc.cluster.local:5432/llmmanager`

## Target State

- **GCP Cloud SQL for PostgreSQL** (single instance, private IP only)
- **Two databases**:
  - `llmmanager` — owned by user `llm` (llm-manager backend)
  - `ecdysis` — owned by user `ecdysis` (ecdysis backend)
- **Connectivity**: Cloud SQL Auth Proxy sidecar in each pod

## Table Ownership

### llm-manager database (`llmmanager`)

| Table | Purpose |
|-------|---------|
| llm_agents | GPU agent registration |
| registered_apps | App registry |
| llm_runners | LLM runner registration |
| profiles | Model profiles |
| profile_model_entries | Profile model config |
| profile_image_entries | Profile image config |
| profile_activations | Active profile tracking |
| app_allowed_models | Per-app model permissions |
| ollama_library_cache | Cached Ollama model library |
| model_safety_tags | Safety classification patterns |
| library_cache_meta | Library cache metadata |
| queue_jobs | Job queue |
| model_settings | Model-specific settings |
| app_rate_limits | Per-app rate limits |

### ecdysis database (`ecdysis`)

| Table | Purpose |
|-------|---------|
| moltbook_configs | Agent configuration (slot 1-6) |
| moltbook_state | Agent runtime state (karma, heartbeat) |
| moltbook_activity | Agent activity log |
| moltbook_peer_posts | Cached peer agent posts |
| moltbook_peer_interactions | Tracked peer interactions |

## Cross-Domain Dependency

`moltbook_configs.llm_runner_id` currently FKs to `llm_runners(id)`.

**After split**: Drop the FK. Moltbook-backend calls llm-manager's
`GET /api/runners` HTTP API to resolve Ollama URLs instead of querying
the table directly. Add `LLM_MANAGER_URL` env var to ecdysis-backend.

## GCP Connectivity: Cloud SQL Auth Proxy Sidecar

No public IPs. Each pod that needs DB access gets a sidecar container:

```yaml
- name: cloud-sql-proxy
  image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:2
  args:
    - "--private-ip"
    - "--port=5432"
    - "amerenda-k3s:us-east1:k3s-dean-postgres"
  env:
    - name: GOOGLE_APPLICATION_CREDENTIALS
      value: /secrets/sa-key.json
  volumeMounts:
    - name: gcp-sa-key
      mountPath: /secrets
      readOnly: true
  resources:
    requests:
      cpu: 10m
      memory: 32Mi
    limits:
      cpu: 100m
      memory: 64Mi
```

App connects to `localhost:5432` — proxy handles auth and tunneling.

### GCP Service Account

Create a service account with `roles/cloudsql.client` permission.
Store the key as a k8s secret (via ExternalSecrets from Bitwarden).

### Docker Compose Compatibility

Same proxy image works in docker-compose as a service:
```yaml
services:
  cloud-sql-proxy:
    image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:2
    command: ["--private-ip", "--address", "0.0.0.0", "--port", "5432", "amerenda-k3s:us-east1:k3s-dean-postgres"]
    volumes:
      - ./gcp-sa-key.json:/secrets/sa-key.json:ro
    environment:
      - GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa-key.json

  app:
    environment:
      - DATABASE_URL=postgresql://user:pass@cloud-sql-proxy:5432/dbname
    depends_on:
      - cloud-sql-proxy
```

## Migration Steps

### Phase 1: Provision GCP Resources — DONE

See [cloud-sql-bootstrap.md](cloud-sql-bootstrap.md) for the full commands.

- [x] Cloud SQL instance `dean-postgres` (PG16, db-f1-micro, us-east1, private IP only)
- [x] Databases: `llmmanager`, `ecdysis`
- [x] Users: `llm`, `ecdysis`
- [x] Service accounts: `k3s-dean-psql` (RW), `k3s-dean-psql-ro` (RO)
- [x] SA keys + passwords + URLs stored in Bitwarden (`dean-` prefix)

### Phase 2: Migrate llm-manager

1. Stop llm-manager backend (scale to 0)
2. `pg_dump` llm-manager tables from local Postgres:
   ```bash
   pg_dump -h localhost -U llm -d llmmanager \
     -t llm_agents -t registered_apps -t llm_runners \
     -t profiles -t profile_model_entries -t profile_image_entries \
     -t profile_activations -t app_allowed_models \
     -t ollama_library_cache -t model_safety_tags -t library_cache_meta \
     -t queue_jobs -t model_settings -t app_rate_limits \
     > llm-manager-dump.sql
   ```
3. Restore to GCP via cloud-sql-proxy:
   ```bash
   psql -h localhost -p 5432 -U llm -d llmmanager < llm-manager-dump.sql
   ```
4. Add cloud-sql-proxy sidecar to llm-manager deployment
5. Update DATABASE_URL secret to `postgresql://llm:PASS@localhost:5432/llmmanager`
6. Scale llm-manager back to 1, verify

### Phase 3: Migrate ecdysis-backend

1. Stop ecdysis-backend (scale to 0)
2. `pg_dump` ecdysis tables:
   ```bash
   pg_dump -h localhost -U llm -d llmmanager \
     -t moltbook_configs -t moltbook_state -t moltbook_activity \
     -t moltbook_peer_posts -t moltbook_peer_interactions \
     > ecdysis-dump.sql
   ```
3. Restore to GCP `ecdysis` database
4. Add cloud-sql-proxy sidecar to ecdysis-backend deployment
5. Update DATABASE_URL to `postgresql://ecdysis:PASS@localhost:5432/ecdysis`
6. Scale back to 1, verify

### Phase 4: Handle llm_runners dependency

1. Add `LLM_MANAGER_URL` env var to ecdysis-backend deployment
   (value: `http://llm-manager-backend.llm-manager.svc.cluster.local:8081`)
2. Update ecdysis-backend code: replace direct `llm_runners` DB reads
   with HTTP call to `GET /api/runners`
3. Drop FK constraint:
   ```sql
   ALTER TABLE moltbook_configs DROP CONSTRAINT IF EXISTS moltbook_configs_llm_runner_id_fkey;
   ```
4. Remove `get_active_runners` and `get_runner_by_id` from ecdysis-backend db.py

### Phase 5: Cleanup

1. Drop ecdysis tables from local Postgres (already removed from llm-manager code)
2. Keep local Postgres running read-only for 1 week as rollback safety
3. After verification period, decommission local Postgres pod
4. Remove postgres deployment/service/PVC from llm-manager k8s manifests

## Rollback

At any phase, flip DATABASE_URL back to local Postgres connection string.
Local Postgres stays running until Phase 5 cleanup.

## Estimated Downtime

- Per app: ~5 minutes (stop, dump, restore, flip, start)
- Can be done during off-hours
- Rollback: instant (env var change + pod restart)

## Cost Estimate

- Cloud SQL db-f1-micro: ~$7/month
- Cloud SQL db-g1-small: ~$25/month
- Storage: $0.17/GB/month (negligible for homelab)
- Cloud SQL Auth Proxy: free (runs as sidecar)
