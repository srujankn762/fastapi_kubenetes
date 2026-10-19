from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor


def setup_telemetry(app, engine):
    # Identify the service in Grafana Tempo
    resource = Resource.create({
        "service.name": "fastapi-backend"
    })

    # Configure the tracer provider
    provider = TracerProvider(resource=resource)

    # Export traces to Grafana Alloy using OTLP/gRPC
    exporter = OTLPSpanExporter(
        endpoint="http://alloy:4317",
        insecure=True,
    )

    # Batch spans before exporting to reduce overhead
    provider.add_span_processor(
        BatchSpanProcessor(exporter)
    )

    # Register the tracer provider
    trace.set_tracer_provider(provider)

    # Automatically trace incoming FastAPI requests
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
    )

    # Automatically trace SQLAlchemy database operations
    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        tracer_provider=provider,
    )