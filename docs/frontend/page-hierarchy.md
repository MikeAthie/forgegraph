# Page Hierarchy

The primary IA follows the company workspace model in [../product/company-workspace-model.md](../product/company-workspace-model.md) and the terminology contract in [../product/canonical-ontology.md](../product/canonical-ontology.md).

## Primary Product Routes

- `/companies`
- `/companies/[companyId]`
- `/runs`
- `/runs/[runId]`
- `/approvals`

## Supporting Operations Routes

- `/departments`
- `/tasks`
- `/memory`
- `/accounting`
- `/library`
- `/credentials`
- `/prompts`

## Advanced And Compatibility Routes

- `/workflows`
- `/graphs`
- `/graphs/[graphId]`
- `/executions`
- `/executions/[executionId]`
- `/inbox`
- `/agents`
- `/overview`

These routes may remain for compatibility, expert workflows, or redirect support. They should not drive primary product language or first-run IA.

## Admin And Specialist Routes

- `/admin/*`
- `/analytics/*`
- `/onboarding`
- `/settings`

## Rule

Default navigation should land the user in company operations, not advanced builder surfaces.
