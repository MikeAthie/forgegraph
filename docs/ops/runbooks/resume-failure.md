# Resume Failure

1. Inspect runs with `recovery_reason=resume_timeout`.
2. Verify `resume_requested` acknowledgements are arriving and match active attempt IDs.
3. Check engine callback authentication and engine ownership logs.
4. Confirm queued recovery or fail-closed behavior is happening as expected.

