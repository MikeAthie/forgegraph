# API Aliases And Deprecations

ForgeGraph keeps compatibility aliases while moving product work toward company-first APIs.

## Primary Product APIs

- `/api/companies/*`
- `/api/company-operations/*`
- `/api/approvals/*`
- `/api/whiteboards/*`
- `/api/communication/*`
- `/api/commerce/*`
- `/api/memory/*`
- `/api/accounting/*`
- `/api/credentials/*`
- `/api/marketplace/*`
- `/api/system-state/*`

## Advanced And Compatibility APIs

- `/api/graphs/*`
- `/api/workflows/*`
- `/api/runs/*`
- `/api/executions/*`
- `/api/decisions/*`
- `/api/agents/*`
- `/api/tasks/*`

These routes can remain live for compatibility, expert tooling, and internal implementation boundaries. New product-facing flows should prefer company, operation, approval, and whiteboard APIs unless they are explicitly testing alias parity.

## Rule

Aliases do not change state ownership. Durable state remains backend-owned, and events or client state must not become authoritative.
