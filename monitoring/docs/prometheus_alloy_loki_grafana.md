# Observability Stack

This directory contains the local observability configuration for the FastAPI application. The stack collects application metrics and container logs, keeps both data types in persistent Docker volumes, and makes them available for inspection through Grafana.

Observability is useful when a backend is more than “up” or “down”: metrics help identify request volume, latency, and errors over time, while logs provide the detailed event context needed to understand an individual failure.

## Components

- **Prometheus** collects time-series metrics by scraping the FastAPI `/metrics` endpoint.
- **Grafana** provides the UI for querying and visualizing metrics and exploring logs. This repository does not include automatic Grafana datasource or dashboard provisioning.
- **Loki** stores the log streams forwarded by Grafana Alloy and serves LogQL queries.
- **Grafana Alloy** discovers Docker containers, reads the selected container's logs through the Docker socket, and pushes them to Loki.


The metrics path is **pull based**: Prometheus periodically requests `/metrics` from `fastapi_backend:8000`. The log path is **push based** from the collector's perspective: Alloy reads the Docker log stream and forwards entries to Loki's push API. Grafana queries Prometheus and Loki; it is not in the ingestion path.

## Technology stack

Versions and host ports below are taken from the root `docker-compose.yaml`.

| Component | Docker image/version | Purpose | Exposed port |
| --- | --- | --- | --- |
| FastAPI backend | Locally built from `fastapi-hello-world/Dockerfile` (`python:3.12-slim`) | Application endpoints and `/metrics` | `8000:8000` |
| Prometheus | `prom/prometheus:v3.5.0` | Metrics scraping and time-series storage | `9090:9090` |
| Grafana | `grafana/grafana:12.1.1` | Metrics visualization and log exploration | `3000:3000` |
| Loki | `grafana/loki:3.5.0` | Log ingestion, indexing, and storage | `127.0.0.1:3100:3100` |
| Grafana Alloy | `grafana/alloy:v1.10.2` | Docker log discovery, collection, and forwarding | None |
| MySQL | `mysql:8.4` | Application database dependency | `3308:3306` |

Loki is bound to loopback on the host, so its port is available locally but is not published on external host interfaces. Alloy has no host port mapping; it communicates with Loki over the internal Compose network.

## Directory structure

```text
.
├── docker-compose.yaml
├── .env                         # Local Compose/database values; do not commit secrets
├── fastapi-hello-world/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       └── main.py              # Instrumentator setup and FastAPI routes
└── monitoring/
    ├── README.md
    ├── prometheus/
    │   └── prometheus.yml       # Scrape interval and FastAPI target
    ├── loki/
    │   └── loki-config.yml      # Local Loki storage and schema
    └── alloy/
        └── config.alloy         # Docker discovery and Loki forwarding
```

There are currently no Grafana provisioning files or dashboard JSON files in the repository. Grafana data is persisted in the `grafana_data` Docker volume instead.

## Configuration explained

### FastAPI instrumentation

`fastapi-hello-world/app/main.py` imports `prometheus_fastapi_instrumentator` and runs:

```python
Instrumentator().instrument(app).expose(app)
```

This instruments the FastAPI application and exposes the `/metrics` endpoint. The dependency is pinned to `prometheus-fastapi-instrumentator==8.1.0` in `requirements.txt`. No custom application metrics are defined in the inspected code; the metrics endpoint is provided by the instrumentator.

The Compose service starts Uvicorn on `0.0.0.0:8000`, making the endpoint available to other Compose services at `http://fastapi_backend:8000/metrics`.

### Prometheus

`monitoring/prometheus/prometheus.yml` defines:

```yaml
global:
  scrape_interval: 15s
```

The `fastapi` scrape job requests the `/metrics` path from `fastapi_backend:8000`. The service name is used instead of `localhost` because Prometheus runs inside its own container. Prometheus stores its TSDB under `/prometheus`, backed by the named `prometheus_data` volume.

### Grafana

Grafana listens on host port `3000` and persists its application state under the named `grafana_data` volume. The Compose file only declares a dependency on Prometheus; it does not provision datasources, dashboards, users, or alert rules.

For a manual local setup, add these datasources in Grafana using the service names reachable from the Compose network:

- Prometheus URL: `http://prometheus:9090`
- Loki URL: `http://loki:3100`

These are connection targets for Grafana inside Docker, not host-browser URLs.

### Loki

`monitoring/loki/loki-config.yml` configures Loki for local development:

- Authentication is disabled with `auth_enabled: false`.
- The HTTP server listens on port `3100`.
- Log chunks and TSDB index data use the local filesystem under `/loki`.
- The configured schema is TSDB `v13`, with daily indexes and filesystem object storage.
- Replication is set to `1` and the ring uses an in-memory key-value store.
- Structured metadata is allowed.

The `/loki` directory is backed by the `loki_data` Docker volume. This is a single-node local-storage configuration, not a highly available or distributed Loki deployment.

### Grafana Alloy

`monitoring/alloy/config.alloy` uses the read-only Docker socket at `/var/run/docker.sock` to discover containers. Its relabel rules keep only the container whose Docker name is exactly `/fastapi-hello-world`, then add the label `job=fastapi`.

The `loki.source.docker` component reads that container's logs and forwards them to `loki.write.default`. Alloy sends the entries to:

```text
http://loki:3100/loki/api/v1/push
```

Alloy state is stored in the `alloy_data` volume. Since the filter is tied to the Compose `container_name`, changing that name requires updating `config.alloy` as well.

### Docker Compose and persistence

The observability services share the default Compose network and use service names for internal communication. Named volumes preserve data across ordinary `docker compose down` and subsequent starts:

| Volume | Data |
| --- | --- |
| `prometheus_data` | Prometheus time-series data |
| `grafana_data` | Grafana state, users, and manually added configuration |
| `loki_data` | Loki chunks, indexes, and rules directory |
| `alloy_data` | Alloy runtime/storage state |

The FastAPI container receives a `DATABASE_URL` assembled from `MYSQL_USER`, `MYSQL_PASSWORD`, and `MYSQL_DATABASE`. MySQL initialization also uses `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_USER`, and `MYSQL_PASSWORD` from the local environment or `.env` file. These variables are application/database configuration; the monitoring services do not consume them.

## Run the stack

From the repository root, ensure Docker Desktop or Docker Engine with Compose is running and that the required MySQL variables are available in `.env` or the shell environment:

```bash
docker compose up --build
```

Useful endpoints after startup:

| URL | Use |
| --- | --- |
| `http://localhost:8000/` | FastAPI root endpoint |
| `http://localhost:8000/metrics` | Prometheus exposition endpoint |
| `http://localhost:9090` | Prometheus UI |
| `http://localhost:3000` | Grafana UI |
| `http://127.0.0.1:3100` | Loki's locally published HTTP endpoint |

Check service status and logs with:

```bash
docker compose ps
docker compose logs -f fastapi_backend
docker compose logs -f alloy
docker compose logs -f loki
```

Stop the services while retaining named-volume data with:

```bash
docker compose down
```

## Verification checklist

1. Open `http://localhost:8000/metrics` and confirm that the FastAPI endpoint returns Prometheus-format text.
2. In Prometheus, open **Status → Targets** and confirm the `fastapi` target is `UP`.
3. In Grafana, add or verify the Prometheus and Loki datasources described above.
4. Generate a request to the API, then inspect Alloy and Loki container logs for collection or delivery errors.
5. In Grafana Explore, select Loki and query the stream with `{job="fastapi"}`.

## Operational notes and limitations

- The stack is configured for local development and learning. Loki has authentication disabled, uses one replica, and stores data on one local filesystem.
- The Docker socket is mounted read-only into Alloy. This enables discovery and log collection but is still a sensitive host-level integration that should be reviewed before production use.
- Only the FastAPI container is collected by Alloy. MySQL, Prometheus, Grafana, Loki, and Alloy logs are not forwarded by this configuration.
- Grafana dashboards and datasources are not version-controlled in this repository, so a new Grafana volume requires manual datasource setup.
- `depends_on` controls startup ordering only; it does not provide a full readiness check for the application, database, Prometheus, or Loki.
- Retention, alert rules, authentication, TLS, and remote object storage are not configured here.

## Related configuration

- [Docker Compose definition](../../docker-compose.yaml)
- [Prometheus configuration](../prometheus/prometheus.yml)
- [Loki configuration](../loki/loki-config.yml)
- [Grafana Alloy configuration](../alloy/config.alloy)
- [FastAPI instrumentation](../../fastapi-hello-world/app/main.py)

