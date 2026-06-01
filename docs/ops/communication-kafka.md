# Communication Kafka Production Notes

ForgeGraph communication Kafka is an optional metadata transport. The backend database outbox and backend receipts remain the only durable authority.

## Production Defaults

- Use managed Kafka with `COMMUNICATION_KAFKA_SECURITY_PROTOCOL=SSL` or `SASL_SSL`.
- Use `SASL_SSL` with `COMMUNICATION_KAFKA_SASL_MECHANISM`, username, and password when the provider requires SASL.
- Run `publish_communication_outbox` and `consume_communication_kafka` as separate workers.
- Enable `READINESS_REQUIRE_COMMUNICATION_KAFKA=true` only for deployments where Kafka is required to be healthy before serving traffic.

## Local Broker

`docker-compose.kafka.yml` is for local Redpanda development and integration smoke tests. It is not the production broker plan.

## Required Checks

- `python manage.py validate_runtime_env --strict`
- Kafka unit tests under `backend/tests/unit/services/test_communication_kafka*.py`
- Optional broker integration with `RUN_KAFKA_INTEGRATION=true` and `KAFKA_BROKERS` configured
