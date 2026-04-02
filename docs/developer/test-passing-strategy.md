# Test Passing Strategy

Priority checks for the OS migration:

- alias routes return compatible data
- projection APIs reconcile with canonical facts
- `/overview`, `/agents`, `/tasks`, `/inbox`, and `/accounting` render with authenticated data
- builder detail flows remain functional through compatibility routes

Do not treat summary correctness as optional. Operator trust depends on it.
