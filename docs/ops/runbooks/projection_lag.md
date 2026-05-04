# Projection Lag

Check `process_os_projections`, projection lag metrics, failed projection
events, database write latency, and the latest projection watermark. HTTP GET
handlers must stay read-only; use the projection worker or backfill command for
rebuilds.
