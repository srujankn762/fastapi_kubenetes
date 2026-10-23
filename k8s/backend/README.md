# FastAPI on Docker Desktop Kubernetes

## Architecture

Only FastAPI runs in Kubernetes. MySQL 8.4 and Prometheus, Grafana, Loki, Alloy, and Tempo remain in Docker Compose. The existing `mysql_data` volume is unchanged. Kubernetes reaches the Compose-published MySQL port and Alloy OTLP receiver through Docker Desktop's `host.docker.internal` host gateway. Prometheus reaches FastAPI through a host port-forward.

The host port listeners for Alloy OTLP and the Prometheus port-forward use all host interfaces because Docker Desktop containers cannot rely on host loopback-only listeners. Use this for trusted local development, and apply host firewall controls on untrusted networks. The MySQL port remains as configured in Compose.

## Prerequisites and files

- Docker Desktop with Kubernetes enabled; verify `kubectl config current-context` is `docker-desktop`.
- `kubectl`, Docker Compose, and the repository's ignored `.env` file with the same MySQL values used to initialize the existing database.
- Files: `deployment.yaml`, `service.yaml`, `configmap.yaml`, and a locally created Secret based on `secret.example.yaml`.

There is no committed `.env.example`. The ConfigMap uses the current non-sensitive database name (`customer_db`); edit it if the existing `.env` uses another value. The Secret must use the existing `MYSQL_USER` and `MYSQL_PASSWORD`; do not change the MySQL volume or initialize a replacement database.

## Start infrastructure and make the image

Start just the Compose services needed by the Kubernetes backend and its observability stack:

```bash
docker compose up -d mysql_database prometheus grafana loki alloy tempo
```

This does not remove or recreate named volumes. Keep the existing `mysql_data` volume. Compose publishes MySQL at host port 3308 and Alloy's OTLP/gRPC port at host port 4317. Compose mode still works with the original backend through its profile:

```bash
docker compose --profile compose-backend up -d
```

For Kubernetes, build into Docker Desktop's image store:

```bash
docker build -t fastapi-backend:dev ./fastapi-hello-world
```

Docker Desktop Kubernetes normally uses the Docker Desktop engine image store. Check `docker context show`, `kubectl config current-context`, and `docker image inspect fastapi-backend:dev` before applying. If you build against a different Docker context, use a GHCR image by changing `image` in `deployment.yaml` to the published immutable commit tag (`ghcr.io/srujankn762/fast-api_kubernetes:<commit-sha>`), and ensure the cluster can pull it. For a private package, create an image pull Secret. The existing GitHub workflow publishes both `latest` and a commit SHA; use the SHA tag for reproducible rollouts.

When rebuilding, prefer an immutable tag:

```bash
IMAGE_TAG="$(git rev-parse --short=12 HEAD)"
docker build -t "fastapi-backend:${IMAGE_TAG}" ./fastapi-hello-world
```

Set that exact image tag in `deployment.yaml` and apply the updated manifest. For an already running Deployment, use `kubectl set image -n fastapi-app deployment/fastapi-backend fastapi="fastapi-backend:${IMAGE_TAG}"` to trigger a rollout. Do not rely on `latest` with `IfNotPresent`.

## Secrets and deployment

Create the namespace and a private local Secret file. Fill it from the same values as the ignored `.env`; never commit the populated file:

```bash
kubectl create namespace fastapi-app
kubectl create secret generic fastapi-backend-secret -n fastapi-app \
  --from-literal=MYSQL_USER='<existing MYSQL_USER>' \
  --from-literal=MYSQL_PASSWORD='<existing MYSQL_PASSWORD>'
```

Do not apply `secret.example.yaml` as working credentials. Apply the ConfigMap, Deployment, and Service:

```bash
kubectl apply -f k8s/backend/configmap.yaml
kubectl apply -f k8s/backend/deployment.yaml
kubectl apply -f k8s/backend/service.yaml
kubectl rollout status -n fastapi-app deployment/fastapi-backend
kubectl get pods -n fastapi-app -o wide
kubectl logs -n fastapi-app deployment/fastapi-backend -f
```

The app builds a SQLAlchemy URL safely from `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`, `DB_HOST`, and `DB_PORT` when `DATABASE_URL` is not set. Compose retains its existing `DATABASE_URL` behavior. No credentials are stored in the ConfigMap or Deployment text.

## API access and Prometheus metrics

Start a host port-forward in a terminal and leave it running:

```bash
kubectl port-forward -n fastapi-app svc/fastapi-backend-service 8001:8000
```

Visit `http://localhost:8001`. Check endpoints:

```bash
curl -fsS http://localhost:8001/health
curl -i http://localhost:8001/customers
curl -fsS http://localhost:8001/metrics
```

The Prometheus scrape target is `host.docker.internal:8001`. For Docker Desktop containers to reach the host forward, start it with a host-wide listener instead:

```bash
kubectl port-forward --address 0.0.0.0 -n fastapi-app svc/fastapi-backend-service 8001:8000
```

Prometheus scrapes `/metrics` every 15 seconds. Open `http://localhost:9090/targets` and check the `fastapi` target. Keep this port-forward running for Prometheus scraping. The host-wide binding can be visible to other machines on the LAN; use a trusted network/firewall.

## Traces and logs

`OTEL_EXPORTER_OTLP_ENDPOINT` is configurable. The Kubernetes ConfigMap points to `http://host.docker.internal:4317`; Alloy forwards received OTLP/gRPC traces to Compose Tempo. View traces in Grafana Explore with the Tempo data source. Confirm Compose has Alloy running and port 4317 published.

Alloy's current Docker discovery continues collecting Compose container logs, but it cannot discover Kubernetes pod logs from the Docker socket. Kubernetes logs are available with `kubectl logs`. Loki ingestion of Kubernetes logs is not configured: reliable collection requires an additional Kubernetes log collector (such as Alloy running as a DaemonSet) with access to node container logs. That collector is intentionally not added here, so existing Loki ingestion remains intact for Docker containers.

## Database migrations

Do not run schema migrations on application startup or in each replica. Review each Alembic revision and run it as a one-off, serialized operation before deploying application code that depends on it. The current Dockerfile copies only requirements and `app/`, not `alembic.ini` or the Alembic directory, so its image cannot currently run `alembic upgrade head`. Run reviewed migrations from the repository's migration-capable environment against the existing `DATABASE_URL`, or extend the image to package Alembic before introducing a Kubernetes Job. Do not apply destructive migrations without a separate review and backup plan.

## Rollout, restart, and rollback

```bash
kubectl rollout restart -n fastapi-app deployment/fastapi-backend
kubectl rollout status -n fastapi-app deployment/fastapi-backend
kubectl rollout history -n fastapi-app deployment/fastapi-backend
kubectl rollout undo -n fastapi-app deployment/fastapi-backend
```

For a specific prior revision, use `kubectl rollout undo -n fastapi-app deployment/fastapi-backend --to-revision=<revision>`. A rollback of application code does not reverse database migrations.

## Troubleshooting

- **ImagePullBackOff:** confirm image tag and image visibility in the Docker Desktop Kubernetes engine; use the GHCR commit tag and configure pull credentials for private packages.
- **MySQL connection failure:** confirm the Compose MySQL container is healthy, host port 3308 is published, ConfigMap DB settings match `.env`, and the Secret matches the existing MySQL user. Check `/db-health`.
- **No traces:** confirm Alloy is running with host port 4317 published and the ConfigMap endpoint is correct; check Alloy and Tempo logs.
- **Prometheus target down:** keep the `kubectl port-forward --address 0.0.0.0` command running, and inspect `http://localhost:9090/targets`.
- **Pod logs in Loki:** this configuration does not collect Kubernetes pod logs; use `kubectl logs` until a Kubernetes log collector is deployed.
- **Compose backend needed:** activate the `compose-backend` profile; the default infrastructure-only command leaves FastAPI out of Compose.
