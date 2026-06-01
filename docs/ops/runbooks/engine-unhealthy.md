# Engine Unhealthy

1. Check engine `/ready`, `/metrics`, and `/health/redis`.
   `/health/redis` reports runtime-intent Redis transport health, not durable
   product-memory state. Durable run, liveness, recovery, snapshot, and memory
   state remain backend-owned.
2. Verify `CONTROL_PLANE_URL`, callback secret, and run-state mode.
3. Inspect callback delivery failures and spool growth.
4. If the image is suspect, redeploy the prior engine image.
