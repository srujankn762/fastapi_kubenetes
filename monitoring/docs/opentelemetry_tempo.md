# OpenTelemetry Tracing with Grafana Tempo

This guide documents the distributed tracing path currently configured for the FastAPI customer API. It focuses on traces; the separate Prometheus and Loki setup is documented in [the metrics and logs guide](prometheus_alloy_loki_grafana.md).

## Overview

[OpenTelemetry](https://opentelemetry.io/) (OTel) is a set of APIs, SDKs, and conventions for creating and exporting telemetry. This application uses its Python SDK and automatic instrumentation to create traces for HTTP requests and SQLAlchemy database operations.

A **distributed trace** records the work caused by one request as a collection of timed spans. Tracing helps answer practical questions: Which part of a request was slow? Did time go to the API handler or the database? Did an operation fail, and where?

| Signal | What it records | Typical question |
| --- | --- | --- |
| Traces | One request's path through operations, with timing and parent/child relationships | Where did this request spend its time? |
| Metrics | Numeric measurements aggregated over time | Are request latency or error rates rising? |
| Logs | Timestamped event messages and details | What did the application report at this moment? |

This project uses OpenTelemetry because automatic instrumentation can connect FastAPI request spans with SQLAlchemy database spans without adding manual tracing calls to each customer route. Grafana Alloy receives and forwards the spans, and Grafana Tempo stores them for exploration. Prometheus metrics and Loki logs use separate pipelines.

## Architecture


1. FastAPI instrumentation creates a server span for an incoming request. SQLAlchemy instrumentation creates spans around database operations performed through the configured engine.
2. The SDK associates spans with the resource name `fastapi-backend`, batches completed spans, and exports them over OTLP/gRPC to `alloy:4317`.
3. Alloy listens for OTLP/gRPC on port `4317` inside the Compose network and exports spans to `tempo:4317`.
4. Tempo stores trace data locally. Grafana queries Tempo's HTTP API at `tempo:3200` and renders traces in Explore.

Compose service names provide DNS between containers on the default network. Alloy's receiver port and Tempo's OTLP port are not published to the host. Tempo's HTTP API is published only on host loopback as `127.0.0.1:3200`.

## OpenTelemetry dependencies

The tracing packages pinned in `fastapi-hello-world/requirements.txt` are:

| Dependency | Version | Purpose |
| --- | --- | --- |
| `opentelemetry-sdk` | `1.45.1` | SDK implementation, tracer provider, resources, and span processing. |
| `opentelemetry-instrumentation-fastapi` | `0.66b1` | Instruments FastAPI requests and creates HTTP/server spans. |
| `opentelemetry-instrumentation-sqlalchemy` | `0.66b1` | Instruments SQLAlchemy engine operations and creates database spans. |
| `opentelemetry-exporter-otlp` | `1.45.1` | OTLP exporters, including the gRPC trace exporter used by the app. |

The instrumentation packages use the OpenTelemetry Python instrumentation release line (`0.66b1`); the SDK and exporter are pinned to `1.45.1`.

## FastAPI instrumentation

`fastapi-hello-world/app/main.py` creates the app, registers the customer router, and enables tracing by calling `setup_telemetry(app, engine)`. The implementation is in [`app/telemetry.py`](../../fastapi-hello-world/app/telemetry.py).

The following excerpt is adapted from that file:

```python
resource = Resource.create({
    "service.name": "fastapi-backend",  # Resource identity shown in Tempo
})

provider = TracerProvider(resource=resource)  # Creates and coordinates spans

exporter = OTLPSpanExporter(
    endpoint="http://alloy:4317",  # Alloy's Compose DNS name and OTLP/gRPC receiver
    insecure=True,                 # Plaintext gRPC for the local Compose network
)

provider.add_span_processor(
    BatchSpanProcessor(exporter)   # Queue spans and export in batches
)

trace.set_tracer_provider(provider)  # Set the process-wide default provider

FastAPIInstrumentor.instrument_app(
    app,
    tracer_provider=provider,       # Trace incoming HTTP requests
)

SQLAlchemyInstrumentor().instrument(
    engine=engine,
    tracer_provider=provider,       # Trace operations on this SQLAlchemy engine
)
```

- **`TracerProvider`** is the SDK entry point that creates tracers and coordinates span processing.
- **`Resource`** identifies the process or service that produced telemetry. Here `service.name` is `fastapi-backend`, the service identity used in Tempo queries.
- **`BatchSpanProcessor`** buffers completed spans and exports them in batches, avoiding a network export for each span.
- **`OTLPSpanExporter`** sends spans using OpenTelemetry Protocol over gRPC. It sends to Alloy, which owns the next hop to Tempo.
- **`FastAPIInstrumentor`** creates spans for incoming HTTP requests.
- **`SQLAlchemyInstrumentor`** instruments the configured engine so SQLAlchemy operations can be represented as spans.

The Compose file bind-mounts `fastapi-hello-world/` at `/app` and starts Uvicorn with `--reload`. Application source changes are therefore visible in this development container; dependency or Dockerfile changes require rebuilding the image.

## Trace and span concepts

A **trace** is the full record of one request. Each trace has a **trace ID**, shared by all its spans. A **span** is one timed operation and has its own **span ID**. Spans have parent/child relationships.

A successful `POST /customers` can produce a trace shaped like this:

```text
Trace (one trace ID)
└── POST /customers                    HTTP server span
    ├── INSERT INTO customers ...      SQLAlchemy database span
    └── SELECT ...                     SQLAlchemy span from db.refresh()
```

The customer handler adds a row, commits it, then refreshes it to read generated values. The HTTP server span is the parent operation; database spans created while it is active can be children in the same trace when context propagation works. Exact database span count and names depend on the SQLAlchemy and driver operations.

- **Trace ID:** Identifies the request across all its spans.
- **Span ID:** Identifies one operation. Its parent span ID links it to the operation that called it.
- **Span duration:** Elapsed time between the start and end of an operation.
- **Span attributes:** Key/value metadata. Instrumentation may attach HTTP method, route, status, database system, and SQL operation attributes. Exact keys depend on instrumentation and semantic convention versions; inspect actual spans before relying on one.
- **Span status:** Describes whether an operation succeeded or failed. Instrumentation can mark errors and attach exception information where supported; this code adds no custom status handling.
- **Context propagation:** Carries the active trace and parent span through instrumented work. FastAPI instrumentation establishes request context, and SQLAlchemy instrumentation uses it for database spans. The repository has no separate cross-service propagation example.

The outline illustrates expected automatic instrumentation. The application does not manually create named business spans.

## Database query tracing

`fastapi-hello-world/app/database.py` creates the SQLAlchemy engine from `DATABASE_URL`. The telemetry setup instruments that engine. SQLAlchemy operations through it can produce database spans, including:

- Operations involved in executing statements through the engine. A span does not necessarily represent all time a pooled connection is idle.
- The `INSERT` generated by `POST /customers`.
- The `SELECT` generated by `GET /customers` or `GET /customers/{customer_id}`.
- Refresh queries after create/update and lookup queries before update/delete.
- Query execution duration and database attributes emitted by the installed instrumentation.

To investigate a slow request, open its trace in Tempo, expand database spans, and compare their duration to the HTTP span. SQL text and parameter values can be omitted or sensitive; inspect emitted attributes rather than assuming a full statement is recorded.

### Deliberately slow query test

There is **no current HTTP endpoint** that executes arbitrary SQL or `SELECT SLEEP(10)`. Running the statement in the MySQL CLI confirms a ten-second database delay, but it does not create an application trace because the query bypasses the instrumented SQLAlchemy engine.

To create a SQLAlchemy trace for this delay, a temporary local-only test harness or route must execute the statement through the app's instrumented engine while a trace context is active. That test harness/route is not implemented in this repository.

```sql
SELECT SLEEP(10);
```

The query deliberately makes MySQL wait for approximately ten seconds so its database span is easy to spot. Use it only in a local test environment. Do not leave an unbounded sleep query in a production route.

## Grafana Alloy configuration

The tracing pipeline in [`monitoring/alloy/config.alloy`](../alloy/config.alloy) is:

```alloy
otelcol.receiver.otlp "default" {
  grpc {
    endpoint = "0.0.0.0:4317" // Listen on the container interface
  }

  output {
    traces = [otelcol.exporter.otlp.tempo.input] // Forward received spans
  }
}

otelcol.exporter.otlp "tempo" {
  client {
    endpoint = "tempo:4317" // Tempo service name and internal OTLP/gRPC port

    tls {
      insecure = true // Plaintext for local Compose networking
    }
  }
}
```

FastAPI sends spans to Alloy so the application only needs a local collector endpoint. The app configures `endpoint="http://alloy:4317"` and `insecure=True`; Alloy listens on `0.0.0.0:4317` and exports to Tempo. Both links use OTLP/gRPC with TLS disabled for this local Compose setup.

Port **4317** is the OTLP/gRPC port in this configuration. Compose DNS names `alloy` and `tempo` resolve between services. The Alloy service has no host `ports:` mapping, so a process running directly on the host cannot reach `alloy:4317` by using that service name.

## Grafana Tempo configuration

Tempo receives spans, stores trace blocks, and serves trace queries to Grafana. The configuration is [`monitoring/tempo/tempo-config.yml`](../tempo/tempo-config.yml):

```yaml
server:
  http_listen_port: 3200       # HTTP API queried by Grafana

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: "0.0.0.0:4317"  # Internal OTLP/gRPC ingestion

storage:
  trace:
    backend: local              # Single-node local storage
    local:
      path: /var/tempo/blocks   # Trace blocks
    wal:
      path: /var/tempo/wal      # Write-ahead log for incoming data
```

Compose runs service `tempo` using `grafana/tempo:2.8.2`. It mounts this config read-only at `/etc/tempo/tempo.yaml` and passes that file to Tempo with `-config.file`. The named `tempo_data` volume is mounted at `/var/tempo`, retaining blocks and WAL when the container is recreated.

Tempo uses HTTP port **3200** for the query/API endpoint and OTLP/gRPC port **4317** for ingestion. Compose publishes `127.0.0.1:3200:3200` only. Alloy reaches Tempo's gRPC receiver through the internal network.

Tempo, Loki, and Prometheus store different signals: Tempo stores traces and span relationships; Loki stores log streams; Prometheus stores numeric time series. Current Compose configuration does not set up automatic trace-to-log or metrics-to-trace links.

## Viewing traces in Grafana

Grafana state is persisted in `grafana_data`, but this repository has no datasource provisioning file. Add Tempo manually if it is not already configured:

1. Open [http://localhost:3000](http://localhost:3000). Grafana credentials are not defined in the checked-in Compose configuration.
2. Go to **Connections → Data sources → Add data source** and select **Tempo**.
3. Set the URL to `http://tempo:3200`. Grafana runs in a container, so this Compose DNS address is appropriate. `localhost:3200` inside Grafana would refer to Grafana itself.
4. Save and test the datasource.
5. Open **Explore** and select Tempo.
6. Run a TraceQL query:

   ```traceql
   { resource.service.name = "fastapi-backend" }
   ```

   Search specifically for create requests:

   ```traceql
   { resource.service.name = "fastapi-backend" && name = "POST /customers" }
   ```

   Search specifically for list requests:

   ```traceql
   { resource.service.name = "fastapi-backend" && name = "GET /customers" }
   ```

7. Select a result to open its trace. The waterfall shows span timing and parent/child structure. Select spans to inspect attributes, status, and duration.

The resource service name is explicitly set to `fastapi-backend`. FastAPI instrumentation generates HTTP span names, which can depend on instrumentation behavior and route naming. Confirm the emitted name in a trace; both service and span names in a query must match actual telemetry.

## Testing distributed tracing

Start the stack from the repository root:

```bash
docker compose up --build
```

The requests below match the actual API routes. They assume MySQL is initialized and the services are ready.

Single GET request:

```bash
curl -i http://localhost:8000/customers
```

Single POST request using the `CustomerCreate` fields (`name`, `age`, `gender`):

```bash
curl -i -X POST http://localhost:8000/customers \
  -H 'Content-Type: application/json' \
  -d '{"name":"Trace Example","age":30,"gender":"unspecified"}'
```

Sequential GET requests produce separate traces:

```bash
for i in 1 2 3 4 5; do
  curl -sS -o /dev/null -w "request $i: %{http_code} %{time_total}s\n" \
    http://localhost:8000/customers
done
```

Concurrent GET requests also produce separate traces:

```bash
for i in 1 2 3 4 5; do
  curl -sS -o /dev/null -w "request $i: %{http_code} %{time_total}s\n" \
    http://localhost:8000/customers &
done
wait
```

Allow a short time for the batch processor to export spans, then search in Grafana. The current API does not expose arbitrary SQL, so the slow-query test requires a temporary SQLAlchemy test harness or route as described above. This MySQL CLI command only demonstrates query delay; it does not produce an app trace:

```bash
docker compose exec mysql_database sh -c \
  'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SELECT SLEEP(10);"'
```

For a ten-second database span, the statement must run through the instrumented application engine with an active trace context.

## Troubleshooting

Run commands from the repository root. Service names below match `docker-compose.yaml`.

| Symptom | Likely cause | Verification | Recommended fix |
| --- | --- | --- | --- |
| Exporter reports `connection refused` to Alloy | Alloy is stopped, starting, or its receiver is not listening. | `docker compose ps alloy fastapi_backend` and `docker compose logs --tail=100 alloy fastapi_backend` | Start Alloy with `docker compose up -d alloy`; confirm receiver `0.0.0.0:4317` and app endpoint `http://alloy:4317`. |
| Alloy reports `lookup tempo ... no such host` | Tempo is stopped, or the service name/network differs. | `docker compose ps tempo alloy` and `docker compose logs --tail=100 tempo alloy` | Start both with `docker compose up -d tempo alloy`; use Compose service name `tempo`. |
| Tempo config path is a directory | Host config file was absent when Compose created the bind mount. | `ls -l monitoring/tempo/tempo-config.yml` and `docker compose logs --tail=100 tempo` | Ensure that path is a regular file; recreate with `docker compose up -d --force-recreate tempo`. |
| Tempo container restarts | Invalid YAML/config, mount issue, or storage startup error. | `docker compose ps -a tempo` and `docker compose logs --tail=200 tempo` | Fix the error reported in logs, confirm the config file and mount, then recreate Tempo. |
| No traces appear in Grafana | No request was made, export failed, datasource is missing, or export batch has not flushed. | `curl -i http://localhost:8000/customers`; then `docker compose logs --tail=100 fastapi_backend alloy tempo` | Generate traffic, wait briefly, add/test the Tempo datasource, and check app/Alloy/Tempo logs. |
| Tempo datasource URL fails | Grafana uses a host-only URL or `localhost` from inside its container. | `docker compose ps grafana tempo`; inspect URL in Grafana. | Set URL to `http://tempo:3200`. For host tools, the published URL is `http://127.0.0.1:3200`. |
| HTTP span exists but SQLAlchemy span is missing | Route uses another engine, setup did not instrument the active engine, or no DB operation ran. | Check `docker compose logs --tail=150 fastapi_backend` and inspect the request trace. | Verify `setup_telemetry(app, engine)` runs and the same `app.database.engine` is passed to `SQLAlchemyInstrumentor().instrument(...)`. |
| TraceQL returns no data | Wrong service/span name, time range, or no traces stored yet. | In Explore broaden the time range and try `{}`; inspect resource attributes and span names on a returned trace. | Generate fresh traffic, use `fastapi-backend` and copy the actual span name from Tempo. |
| App changes do not appear in Docker | Wrong Compose project, reload issue, or changes affect dependencies/image rather than mounted source. | `docker compose ps fastapi_backend` and `docker compose logs --tail=100 fastapi_backend` | Compose bind-mounts source at `/app` and runs Uvicorn `--reload`. Rebuild dependency/image changes with `docker compose up --build -d fastapi_backend`. |

When FastAPI runs on the host rather than in Compose, `alloy` does not resolve as a host DNS name. The current Alloy receiver is not published to the host; host-based development would require an intentional networking change.

## Production considerations

These entries distinguish current behavior from potential improvements; they do not describe features already configured.

| Area | Current implementation | Future production work |
| --- | --- | --- |
| Sampling | No sampler is configured explicitly; SDK defaults apply. | Choose a policy for traffic volume and diagnostic needs. Head sampling reduces volume; tail sampling requires collector-side design. |
| Instrumentation overhead | FastAPI and SQLAlchemy auto-instrumentation are enabled; spans are batched. | Measure latency, CPU, memory, and span volume under representative traffic. |
| Sensitive attributes | No custom span attributes are added. Automatic instrumentation can still emit request/database metadata. | Review actual attributes and redact credentials, personal data, query parameters, or SQL values as needed. |
| TLS and authentication | Both OTLP links use plaintext. Tempo auth is disabled. Host-published Tempo HTTP is loopback-bound. | Add TLS, authentication, and network controls across trust boundaries. |
| Retention and storage | Tempo uses local blocks and WAL in persistent `tempo_data`; no retention policy is configured. | Define retention, capacity, backups, and suitable production storage. |
| Resource usage | No Compose resource limits are set for the tracing services. | Size collector/backend and set resource limits and storage/queue alerts. |
| Batch exporting | App uses `BatchSpanProcessor`. | Tune queue, batch size, and timeouts; ensure process shutdown flushes spans. |
| Export errors | No app-specific retry, fallback, or alerting policy is defined in `setup_telemetry`. | Monitor export failures and define acceptable retry and data-loss behavior. |
| Trace-to-log correlation | Docker logs are collected independently; trace IDs are not added to log records and Grafana links are not configured. | Add trace/span IDs to structured logs and configure navigation between traces and related logs. |

## Related files

- [FastAPI app initialization and routes](../../fastapi-hello-world/app/main.py)
- [OpenTelemetry setup](../../fastapi-hello-world/app/telemetry.py)
- [SQLAlchemy engine and sessions](../../fastapi-hello-world/app/database.py)
- [Customer routes](../../fastapi-hello-world/app/routers/customer.py)
- [Customer request/response schemas](../../fastapi-hello-world/app/schemas/customer.py)
- [Python requirements](../../fastapi-hello-world/requirements.txt)
- [Docker Compose services and volumes](../../docker-compose.yaml)
- [Alloy config](../alloy/config.alloy)
- [Tempo config](../tempo/tempo-config.yml)
- [Metrics and logs guide](prometheus_alloy_loki_grafana.md)

