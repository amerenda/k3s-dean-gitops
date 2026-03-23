# Cloud SQL Bootstrap

Commands to provision the GCP Cloud SQL instance for the dean cluster.
Project: `amerenda-k3s`, Region: `us-east1`, Instance: `dean-postgres`.

## Prerequisites: Enable APIs

```bash
gcloud services enable sqladmin.googleapis.com --project=amerenda-k3s
gcloud services enable servicenetworking.googleapis.com --project=amerenda-k3s
gcloud services enable compute.googleapis.com --project=amerenda-k3s
```

## VPC Peering for Private IP

Cloud SQL private IP requires a peered IP range on the default VPC:

```bash
gcloud compute addresses create google-managed-services-default \
  --global \
  --purpose=VPC_PEERING \
  --prefix-length=16 \
  --network=default \
  --project=amerenda-k3s

gcloud services vpc-peerings connect \
  --service=servicenetworking.googleapis.com \
  --ranges=google-managed-services-default \
  --network=default \
  --project=amerenda-k3s
```

## Create Cloud SQL Instance

Private IP only, no public IP. The Cloud SQL Auth Proxy handles connectivity.

```bash
gcloud sql instances create dean-postgres \
  --project=amerenda-k3s \
  --database-version=POSTGRES_16 \
  --region=us-east1 \
  --edition=ENTERPRISE \
  --tier=db-f1-micro \
  --storage-type=SSD \
  --storage-size=10GB \
  --storage-auto-increase \
  --availability-type=zonal \
  --no-assign-ip \
  --network=projects/amerenda-k3s/global/networks/default \
  --enable-google-private-path \
  --database-flags=log_min_duration_statement=1000
```

## Create Databases

```bash
gcloud sql databases create llmmanager --instance=dean-postgres --project=amerenda-k3s
gcloud sql databases create ecdysis --instance=dean-postgres --project=amerenda-k3s
```

## Create Database Users

```bash
LLM_PASS=$(openssl rand -base64 24)
ECDYSIS_PASS=$(openssl rand -base64 24)

echo "llm password: $LLM_PASS"
echo "ecdysis password: $ECDYSIS_PASS"

gcloud sql users create llm \
  --instance=dean-postgres \
  --password="$LLM_PASS" \
  --project=amerenda-k3s

gcloud sql users create ecdysis \
  --instance=dean-postgres \
  --password="$ECDYSIS_PASS" \
  --project=amerenda-k3s
```

## Create Service Accounts

### Read-write (used by app pods via Cloud SQL Auth Proxy)

```bash
gcloud iam service-accounts create k3s-dean-psql \
  --display-name="k3s dean postgres read-write" \
  --project=amerenda-k3s

gcloud projects add-iam-policy-binding amerenda-k3s \
  --member="serviceAccount:k3s-dean-psql@amerenda-k3s.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

gcloud iam service-accounts keys create /tmp/k3s-dean-psql-key.json \
  --iam-account=k3s-dean-psql@amerenda-k3s.iam.gserviceaccount.com
```

### Read-only (for future use)

```bash
gcloud iam service-accounts create k3s-dean-psql-ro \
  --display-name="k3s dean postgres read-only" \
  --project=amerenda-k3s

gcloud projects add-iam-policy-binding amerenda-k3s \
  --member="serviceAccount:k3s-dean-psql-ro@amerenda-k3s.iam.gserviceaccount.com" \
  --role="roles/cloudsql.viewer"

gcloud iam service-accounts keys create /tmp/k3s-dean-psql-ro-key.json \
  --iam-account=k3s-dean-psql-ro@amerenda-k3s.iam.gserviceaccount.com
```

## Bitwarden Secrets

Store these in Bitwarden (one value per secret, `dean-` prefix):

| Bitwarden Key | Value |
|---|---|
| `dean-cloud-sql-llm-password` | Password for `llm` DB user |
| `dean-cloud-sql-ecdysis-password` | Password for `ecdysis` DB user |
| `dean-cloud-sql-sa-key` | Contents of `/tmp/k3s-dean-psql-key.json` |
| `dean-cloud-sql-sa-key-ro` | Contents of `/tmp/k3s-dean-psql-ro-key.json` |
| `dean-cloud-sql-llm-url` | `postgresql://llm:PASSWORD@127.0.0.1:5432/llmmanager` |
| `dean-cloud-sql-ecdysis-url` | `postgresql://ecdysis:PASSWORD@127.0.0.1:5432/ecdysis` |

Replace `PASSWORD` in the URLs with the actual passwords.

## Cleanup

```bash
rm /tmp/k3s-dean-psql-key.json /tmp/k3s-dean-psql-ro-key.json
```

## Connection Name

Used in Cloud SQL Auth Proxy sidecar config:

```
amerenda-k3s:us-east1:dean-postgres
```
