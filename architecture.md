
# ForgeGraph Architecture

This document defines the Clean Architecture structure for ForgeGraph. All code must follow these boundaries.

---

## Clean Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Frameworks & Drivers (Outer)                         │
│  Django, DRF, PostgreSQL, Redis, Next.js, gRPC, HTTP clients, Docker        │
├─────────────────────────────────────────────────────────────────────────────┤
│                          Interface Adapters                                  │
│  Controllers, Presenters, Gateways, Serializers, Repositories               │
├─────────────────────────────────────────────────────────────────────────────┤
│                      Application Business Rules                              │
│  Use Cases, Application Services, DTOs, Ports (interfaces)                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                      Enterprise Business Rules (Core)                        │
│  Entities, Value Objects, Domain Services, Domain Events                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Dependency Rule:** Dependencies point inward. Inner layers know nothing about outer layers.

---

## Execution Model

ForgeGraph uses a **schema-driven, LangGraph-style runtime** with an **n8n-inspired UX**. Users build workflows as directed graphs of Nodes connected by Edges.

### Core Principles

- **Agnostic execution primitives** - A small, stable set of node types that can express most workflows
- **Schema-first reliability** - Outputs can be validated and structured to reduce hallucinations
- **N8n-like UX, LangGraph-like semantics** - Easy graph building with real runtime logic
- **State-driven execution** - Nodes read from and write to a shared run state

### Runtime State

The execution engine maintains a shared state map:

- `state["node.<id>.output"]` - Node execution output
- `state["vars.<name>"]` - Computed variables from transform nodes
- `state["input.<name>"]` - Run input values

### Execution Flow

1. **Start Nodes** - Any node with no incoming edges (indegree = 0). Multiple start nodes run in parallel.
2. **Scheduling** - Queue-based with worker pool. Nodes become ready when all upstream dependencies are satisfied.
3. **Branching** - Branch nodes evaluate boolean conditions and activate exactly one outgoing edge path (true/false).
4. **Merging** - Merge nodes wait until all incoming branches complete, then continue downstream.

### Node Types

| Node | Description |
|------|-------------|
| **Prompt** | Calls LLM with structured instructions, can target an output schema, writes validated output to state |
| **Tool (HTTP)** | Generic tool executor (HTTP as baseline), writes response to state |
| **Transform** | Deterministic state transforms (mapping, formatting, extraction), writes derived values to state |
| **Branch** | Evaluates conditions → routes execution to exactly one path |
| **Merge** | Waits for multiple inputs → continues downstream (synchronization barrier) |
| **Human Gate** | Pauses run → resumes on approval/input |
| **Output** | Collects + validates final result → ends run |

---

## Layer Definitions

### 1. Enterprise Business Rules (Entities)

Pure business logic with no external dependencies. These are the core domain objects.

**Contains:**

- Entities (Graph, GraphVersion, PromptTemplate, Run, NodeRun, User)
- Value Objects (NodeConfig, EdgeDefinition, RetryPolicy, RunStatus)
- Domain Services (GraphValidator, ExecutionPlanner)
- Domain Events (RunStarted, NodeCompleted, RunFailed)

**Rules:**

- No imports from Django, DRF, or any framework
- No database access
- No HTTP/gRPC knowledge
- Pure Python with type hints
- Can raise domain-specific exceptions

### 2. Application Business Rules (Use Cases)

Application-specific business rules. Orchestrates entities to achieve goals.

**Contains:**

- Use Cases (CreateGraph, StartRun, ClonePrompt, ResumeRun)
- Application Services (AuthService, GraphService, PromptService, RunService)
- Ports (interfaces for repositories, external services)
- DTOs (Data Transfer Objects for input/output)

**Rules:**

- Imports from Entities layer only
- Defines interfaces (ports) that adapters must implement
- No framework imports
- No knowledge of HTTP, gRPC, or database specifics

### 3. Interface Adapters

Converts data between use cases and external agencies.

**Contains:**

- Controllers (Django views/viewsets that call use cases)
- Presenters (format use case output for responses)
- Gateways (implement ports for external services: LLM, HTTP APIs)
- Repositories (implement ports for data persistence)
- Serializers (DRF serializers for request/response)

**Rules:**

- Imports from Use Cases and Entities layers
- Can import framework code (Django, DRF)
- Implements ports defined in Use Cases layer
- Translates between domain objects and external formats

### 4. Frameworks & Drivers

External tools, frameworks, and delivery mechanisms.

**Contains:**

- Django settings, URLs, WSGI
- DRF routers and authentication
- Database models (Django ORM) and migrations
- Next.js pages and components
- gRPC server and protobuf definitions
- Docker configuration
- External API clients

**Rules:**

- Can import from all layers
- Contains framework-specific configuration
- Thin layer that delegates to adapters

---

## Backend Directory Structure (Django)

```text
backend/
├── manage.py
├── requirements.txt
├── Dockerfile
├── pytest.ini
│
├── config/                          # Frameworks & Drivers
│   ├── __init__.py
│   ├── settings.py                  # Django settings
│   ├── urls.py                      # Root URL configuration
│   ├── wsgi.py
│   └── asgi.py
│
├── domain/                          # Enterprise Business Rules
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── user.py                  # User entity
│   │   ├── graph.py                 # Graph, GraphVersion entities
│   │   ├── prompt.py                # PromptTemplate entity
│   │   └── run.py                   # Run, NodeRun entities
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── node_types.py            # NodeType enum, NodeConfig
│   │   ├── edge.py                  # EdgeDefinition
│   │   ├── run_status.py            # RunStatus enum
│   │   └── retry_policy.py          # RetryPolicy
│   ├── services/
│   │   ├── __init__.py
│   │   ├── graph_validator.py       # Validates graph structure (DAG, nodes, edges)
│   │   └── execution_planner.py     # Builds execution plan from graph
│   ├── events/
│   │   ├── __init__.py
│   │   └── run_events.py            # Domain events for runs
│   └── exceptions.py                # Domain-specific exceptions
│
├── application/                     # Application Business Rules
│   ├── __init__.py
│   ├── ports/                       # Interfaces (abstract base classes)
│   │   ├── __init__.py
│   │   ├── repositories.py          # IUserRepository, IGraphRepository, etc.
│   │   ├── services.py              # IAuthService, IEngineClient, etc.
│   │   └── unit_of_work.py          # IUnitOfWork for transactions
│   ├── use_cases/
│   │   ├── __init__.py
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── register_user.py
│   │   │   ├── login_user.py
│   │   │   └── get_current_user.py
│   │   ├── graphs/
│   │   │   ├── __init__.py
│   │   │   ├── create_graph.py
│   │   │   ├── update_graph.py
│   │   │   ├── delete_graph.py
│   │   │   ├── list_graphs.py
│   │   │   ├── get_graph.py
│   │   │   ├── create_graph_version.py
│   │   │   └── get_graph_version.py
│   │   ├── prompts/
│   │   │   ├── __init__.py
│   │   │   ├── create_prompt.py
│   │   │   ├── update_prompt.py
│   │   │   ├── delete_prompt.py
│   │   │   ├── list_prompts.py
│   │   │   ├── get_prompt.py
│   │   │   ├── clone_prompt.py
│   │   │   └── publish_prompt.py
│   │   └── runs/
│   │       ├── __init__.py
│   │       ├── start_run.py
│   │       ├── get_run.py
│   │       ├── list_runs.py
│   │       ├── cancel_run.py
│   │       └── resume_run.py
│   ├── dto/
│   │   ├── __init__.py
│   │   ├── auth.py                  # RegisterInput, LoginInput, UserOutput
│   │   ├── graph.py                 # GraphInput, GraphOutput, GraphVersionInput
│   │   ├── prompt.py                # PromptInput, PromptOutput
│   │   └── run.py                   # RunInput, RunOutput
│   └── services/
│       ├── __init__.py
│       └── password_hasher.py       # IPasswordHasher interface
│
├── adapters/                        # Interface Adapters
│   ├── __init__.py
│   ├── api/                         # Controllers (Django REST Framework)
│   │   ├── __init__.py
│   │   ├── auth/
│   │   │   ├── __init__.py
│   │   │   ├── views.py             # AuthViewSet
│   │   │   ├── serializers.py
│   │   │   └── urls.py
│   │   ├── graphs/
│   │   │   ├── __init__.py
│   │   │   ├── views.py             # GraphViewSet, GraphVersionViewSet
│   │   │   ├── serializers.py
│   │   │   └── urls.py
│   │   ├── prompts/
│   │   │   ├── __init__.py
│   │   │   ├── views.py             # PromptViewSet
│   │   │   ├── serializers.py
│   │   │   └── urls.py
│   │   ├── runs/
│   │   │   ├── __init__.py
│   │   │   ├── views.py             # RunViewSet
│   │   │   ├── serializers.py
│   │   │   └── urls.py
│   │   └── urls.py                  # Combines all API URLs
│   ├── repositories/                # Repository implementations
│   │   ├── __init__.py
│   │   ├── django_user_repository.py
│   │   ├── django_graph_repository.py
│   │   ├── django_prompt_repository.py
│   │   └── django_run_repository.py
│   ├── gateways/                    # External service adapters
│   │   ├── __init__.py
│   │   └── grpc_engine_client.py    # Calls Go engine via gRPC
│   └── presenters/                  # Output formatters
│       ├── __init__.py
│       ├── graph_presenter.py
│       ├── prompt_presenter.py
│       └── run_presenter.py
│
├── infrastructure/                  # Frameworks & Drivers
│   ├── __init__.py
│   ├── orm/                         # Django ORM models
│   │   ├── __init__.py
│   │   ├── models.py                # All Django models
│   │   └── admin.py                 # Django admin configuration
│   ├── migrations/                  # Django migrations
│   │   └── ...
│   ├── auth/                        # Django auth configuration
│   │   ├── __init__.py
│   │   ├── backends.py              # Custom auth backends
│   │   └── jwt.py                   # JWT configuration
│   └── seed/                        # Seed data
│       ├── __init__.py
│       └── prompts.py               # Built-in prompt templates
│
└── tests/
    ├── __init__.py
    ├── conftest.py                  # Pytest fixtures
    ├── unit/                        # Unit tests (domain, use cases)
    │   ├── domain/
    │   └── application/
    ├── integration/                 # Integration tests (repositories, APIs)
    │   ├── adapters/
    │   └── infrastructure/
    └── factories.py                 # Test factories
```

---

## Engine Directory Structure (Go)

```text
engine/
├── main.go
├── go.mod
├── go.sum
├── Dockerfile
│
├── proto/                           # Frameworks & Drivers
│   └── engine.proto                 # gRPC service definitions
│
├── domain/                          # Enterprise Business Rules
│   ├── entity/
│   │   ├── graph.go                 # Graph, Node, Edge structs
│   │   ├── run.go                   # Run, NodeRun structs
│   │   └── state.go                 # Execution state
│   ├── value/
│   │   ├── node_type.go             # NodeType enum
│   │   ├── run_status.go            # RunStatus enum
│   │   └── retry_policy.go          # RetryPolicy struct
│   ├── service/
│   │   ├── graph_validator.go       # Validates DAG structure
│   │   ├── execution_planner.go     # Builds execution order
│   │   └── condition_evaluator.go   # Evaluates branch conditions
│   └── errors.go                    # Domain errors
│
├── application/                     # Application Business Rules
│   ├── port/
│   │   ├── repository.go            # RunRepository interface
│   │   ├── node_executor.go         # NodeExecutor interface
│   │   └── llm_client.go            # LLMClient interface
│   ├── usecase/
│   │   ├── start_run.go
│   │   ├── cancel_run.go
│   │   ├── resume_run.go
│   │   └── get_run.go
│   └── dto/
│       ├── run.go
│       └── node.go
│
├── adapter/                         # Interface Adapters
│   ├── grpc/                        # gRPC handlers (controllers)
│   │   ├── server.go
│   │   └── handler.go
│   ├── repository/                  # Repository implementations
│   │   └── postgres_run_repository.go
│   ├── executor/                    # Node executor implementations
│   │   ├── prompt_executor.go
│   │   ├── http_executor.go
│   │   ├── transform_executor.go
│   │   ├── branch_executor.go
│   │   ├── merge_executor.go
│   │   └── output_executor.go
│   └── gateway/                     # External service clients
│       ├── openai_client.go
│       └── http_client.go
│
└── infrastructure/                  # Frameworks & Drivers
    ├── config/
    │   └── config.go                # Configuration loading
    ├── db/
    │   └── postgres.go              # Database connection
    └── grpc/
        ├── engine.pb.go             # Generated protobuf
        └── engine_grpc.pb.go        # Generated gRPC
```

---

## Frontend Directory Structure (Next.js)

```text
frontend/
├── package.json
├── next.config.js
├── Dockerfile
│
├── pages/                           # Frameworks & Drivers (Next.js routing)
│   ├── _app.js
│   ├── index.js
│   ├── login.js
│   ├── register.js
│   ├── graphs/
│   │   ├── index.js                 # Graph list
│   │   └── [id].js                  # Graph editor (Phase 2)
│   └── prompts/
│       └── index.js                 # Prompt library
│
├── domain/                          # Enterprise Business Rules
│   ├── entities/
│   │   ├── user.ts
│   │   ├── graph.ts
│   │   ├── prompt.ts
│   │   └── run.ts
│   └── value-objects/
│       ├── node-types.ts
│       └── run-status.ts
│
├── application/                     # Application Business Rules
│   ├── ports/
│   │   ├── auth-service.ts          # IAuthService interface
│   │   ├── graph-service.ts         # IGraphService interface
│   │   └── prompt-service.ts        # IPromptService interface
│   ├── use-cases/
│   │   ├── auth/
│   │   ├── graphs/
│   │   └── prompts/
│   └── dto/
│       ├── auth.ts
│       ├── graph.ts
│       └── prompt.ts
│
├── adapters/                        # Interface Adapters
│   ├── api/                         # API client implementations
│   │   ├── client.ts                # Axios instance with interceptors
│   │   ├── auth-api.ts              # Implements IAuthService
│   │   ├── graph-api.ts             # Implements IGraphService
│   │   └── prompt-api.ts            # Implements IPromptService
│   └── presenters/
│       ├── graph-presenter.ts
│       └── prompt-presenter.ts
│
├── infrastructure/                  # Frameworks & Drivers
│   ├── auth/
│   │   └── auth-context.tsx         # React context for auth state
│   └── config/
│       └── api-config.ts            # API base URL, etc.
│
├── components/                      # UI Components (Frameworks layer)
│   ├── common/
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Modal.tsx
│   │   └── LoadingSpinner.tsx
│   ├── layout/
│   │   ├── Header.tsx
│   │   ├── Navigation.tsx
│   │   └── Layout.tsx
│   ├── auth/
│   │   ├── LoginForm.tsx
│   │   └── RegisterForm.tsx
│   ├── graphs/
│   │   ├── GraphList.tsx
│   │   ├── GraphCard.tsx
│   │   └── CreateGraphModal.tsx
│   └── prompts/
│       ├── PromptList.tsx
│       ├── PromptCard.tsx
│       ├── PromptDetail.tsx
│       └── CreatePromptModal.tsx
│
├── hooks/                           # React hooks
│   ├── useAuth.ts
│   ├── useGraphs.ts
│   └── usePrompts.ts
│
└── styles/
    └── globals.css
```

---

## Data Flow Example

### Creating a Graph (Backend)

```text
1. HTTP Request → POST /api/graphs/
                        ↓
2. Framework     → DRF Router → GraphViewSet.create()
                        ↓
3. Adapter       → GraphSerializer validates input
                 → Converts to CreateGraphInput DTO
                        ↓
4. Use Case      → CreateGraphUseCase.execute(input, user_id)
                 → Creates Graph entity
                 → Validates with GraphValidator (domain service)
                        ↓
5. Adapter       → IGraphRepository.save(graph)
                 → DjangoGraphRepository converts to ORM model
                        ↓
6. Framework     → Django ORM saves to PostgreSQL
                        ↓
7. Return path   → Repository returns Graph entity
                 → Use case returns GraphOutput DTO
                 → Presenter formats response
                 → Serializer converts to JSON
                        ↓
8. HTTP Response → 201 Created with graph JSON
```

### Starting a Run (Engine)

```text
1. gRPC Request  → StartRun(graph_version_id, input)
                        ↓
2. Framework     → gRPC Server → Handler.StartRun()
                        ↓
3. Adapter       → Converts protobuf to StartRunInput DTO
                        ↓
4. Use Case      → StartRunUseCase.Execute(input)
                 → Loads graph from repository
                 → Validates graph (domain service)
                 → Creates execution plan
                 → Creates Run entity
                        ↓
5. Adapter       → IRunRepository.Save(run)
                 → PostgresRunRepository writes to DB
                        ↓
6. Use Case      → Spawns goroutines for execution
                 → Executes nodes via INodeExecutor
                 → Updates NodeRun records
                        ↓
7. Return path   → Returns RunOutput DTO
                 → Converts to protobuf
                        ↓
8. gRPC Response → StartRunResponse with run_id
```

---

## Key Principles

### 1. Dependency Injection

All adapters receive their dependencies via constructor injection:

```python
# Python example
class CreateGraphUseCase:
    def __init__(
        self,
        graph_repository: IGraphRepository,
        graph_validator: GraphValidator,
    ):
        self._graph_repository = graph_repository
        self._graph_validator = graph_validator
```

```go
// Go example
type StartRunUseCase struct {
    runRepo      port.RunRepository
    graphLoader  port.GraphLoader
    nodeExecutor port.NodeExecutor
}
```

### 2. Interface Segregation

Define small, focused interfaces:

```python
# Good
class IGraphRepository(ABC):
    @abstractmethod
    def get_by_id(self, id: UUID) -> Optional[Graph]: ...

    @abstractmethod
    def save(self, graph: Graph) -> Graph: ...

    @abstractmethod
    def delete(self, id: UUID) -> None: ...

# Bad - too many responsibilities
class IRepository(ABC):
    # Users, Graphs, Prompts, Runs all in one interface
```

### 3. Entity Independence

Entities must not depend on frameworks:

```python
# Good - pure Python
@dataclass
class Graph:
    id: UUID
    owner_id: UUID
    name: str
    description: str
    created_at: datetime

# Bad - Django dependency
class Graph(models.Model):
    # This belongs in infrastructure/orm/models.py
```

### 4. Use Case Single Responsibility

Each use case does one thing:

```python
# Good
class CreateGraph: ...
class UpdateGraph: ...
class DeleteGraph: ...

# Bad
class GraphCRUD:
    def create(self): ...
    def read(self): ...
    def update(self): ...
    def delete(self): ...
```

### 5. DTOs at Boundaries

Use DTOs to cross layer boundaries:

```python
# Input DTO (from controller to use case)
@dataclass
class CreateGraphInput:
    name: str
    description: str

# Output DTO (from use case to presenter)
@dataclass
class GraphOutput:
    id: UUID
    name: str
    description: str
    created_at: datetime
    version_count: int
```

---

## Testing Strategy

### Unit Tests (domain/, application/)

- Test entities and value objects
- Test domain services
- Test use cases with mocked repositories
- No database, no HTTP

### Integration Tests (adapters/)

- Test repositories with real database
- Test API endpoints end-to-end
- Test gRPC handlers

### Contract Tests

- Verify API contracts match frontend expectations
- Verify gRPC contracts between Django and Go

---

## Migration Path from Current Scaffold

The current scaffold has a flat structure. Migrate as follows:

1. Create the directory structure above
2. Move `backend/app/` code to appropriate layers
3. Create domain entities as pure Python classes
4. Create Django ORM models in infrastructure that map to entities
5. Implement repositories that convert between ORM and entities
6. Create use cases that orchestrate business logic
7. Refactor views to be thin controllers that call use cases

---

## References

- Clean Architecture by Robert C. Martin
- Cosmic Python (Architecture Patterns with Python)
- Domain-Driven Design by Eric Evans
