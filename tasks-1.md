# Phase 1 — Django Control Plane Core

**Goal:** Product backbone and persistence.

**Deliverable:** You can log in, create and store graph JSON, and browse the prompt library.

---

## 1. Django Project Setup

- [x] 1.1 Create Django app structure for control plane (Clean Architecture)
  - [x] Create `config/` for Django settings, urls, wsgi, asgi
  - [x] Create `domain/` for entities, value objects, services, events, exceptions
  - [x] Create `application/` for ports, use cases, DTOs
  - [x] Create `adapters/` for API views, repositories, gateways, presenters
  - [x] Create `infrastructure/orm/` for Django ORM models (User, Graph, Prompt, Run)
  - [x] Create `tests/` for unit and integration tests
- [x] 1.2 Install and configure Django REST Framework
  - [x] Add `djangorestframework` to requirements.txt
  - [x] Add `djangorestframework-simplejwt` to requirements.txt
  - [x] Add `django-cors-headers` to requirements.txt
  - [x] Configure DRF in settings.py (default authentication, permissions, pagination)
  - [x] Configure CORS for frontend (localhost:3000)
- [x] 1.3 Configure PostgreSQL connection
  - [x] Update settings.py to use environment variables for DB config
  - [x] Verify connection works with `./dev up`
- [x] 1.4 Set up Django admin
  - [x] Register all models with admin site
  - [x] Create initial superuser via migration or command

---

## 2. Authentication System

- [x] 2.1 Install authentication packages
  - [x] Add `djangorestframework-simplejwt` to requirements.txt
  - [ ] Add `django-allauth` to requirements.txt (optional, for future OAuth)
- [x] 2.2 Create custom User model
  - [x] Extend AbstractUser in infrastructure/orm/models.py
  - [x] Fields: id (uuid), email (unique), password, created_at
  - [x] Set AUTH_USER_MODEL in settings.py
- [x] 2.3 Create authentication endpoints
  - [x] POST /api/auth/register - create new user
  - [x] POST /api/auth/login - obtain JWT tokens
  - [x] POST /api/auth/refresh - refresh access token
  - [x] POST /api/auth/logout - blacklist refresh token
  - [x] GET /api/auth/me - get current user info
- [x] 2.4 Create authentication serializers
  - [x] RegisterSerializer
  - [x] LoginSerializer
  - [x] UserSerializer (for /me endpoint)
- [x] 2.5 Configure JWT settings
  - [x] Set token expiry times (access: 15min, refresh: 7 days)
  - [x] Configure token blacklist for logout
- [x] 2.6 Add authentication middleware
  - [x] Ensure all /api/* routes require authentication (except auth endpoints)
- [x] 2.7 Write authentication tests
  - [x] Test registration flow
  - [x] Test login/logout flow
  - [x] Test token refresh
  - [x] Test protected endpoint access

---

## 3. Data Models

### 3.1 Graph Models (graphs app)

- [x] 3.1.1 Create Graph model
  - [x] id (UUIDField, primary key)
  - [x] owner (ForeignKey to User)
  - [x] name (CharField, max 255)
  - [x] description (TextField, blank=True)
  - [x] created_at (DateTimeField, auto_now_add)
  - [x] updated_at (DateTimeField, auto_now)
- [x] 3.1.2 Create GraphVersion model
  - [x] id (UUIDField, primary key)
  - [x] graph (ForeignKey to Graph, related_name='versions')
  - [x] version (PositiveIntegerField)
  - [x] graph_json (JSONField) - stores nodes, edges, metadata
  - [x] checksum (CharField, max 64, blank=True) - SHA256 of graph_json
  - [x] created_at (DateTimeField, auto_now_add)
  - [x] Add unique_together constraint: (graph, version)
- [x] 3.1.3 Create migrations for graph models
- [x] 3.1.4 Add model managers
  - [x] GraphManager with `for_user(user)` queryset method
  - [x] GraphVersionManager with `latest_for_graph(graph_id)` method

### 3.2 Prompt Models (prompts app)

- [x] 3.2.1 Create PromptTemplate model
  - [x] id (UUIDField, primary key)
  - [x] owner (ForeignKey to User, null=True, blank=True) - null for built-in
  - [x] title (CharField, max 255)
  - [x] description (TextField, blank=True)
  - [x] category (CharField, choices: research, summarization, email, extraction, reasoning, other)
  - [x] content (TextField) - the prompt template text
  - [x] variables_schema (JSONField, blank=True) - describes expected variables
  - [x] version (CharField, max 32, default='1.0.0')
  - [x] license (CharField, max 64, default='MIT')
  - [x] visibility (CharField, choices: private, public, default='private')
  - [x] created_at (DateTimeField, auto_now_add)
  - [x] updated_at (DateTimeField, auto_now)
- [x] 3.2.2 Create migrations for prompt models
- [x] 3.2.3 Add model managers
  - [x] PromptTemplateManager with `public()` and `for_user(user)` methods
- [x] 3.2.4 Add model methods
  - [x] `clone_for_user(user)` - creates user copy of a template

### 3.3 Run Models (runs app - stub)

- [x] 3.3.1 Create Run model (stub for Phase 4)
  - [x] id (UUIDField, primary key)
  - [x] owner (ForeignKey to User)
  - [x] graph_version (ForeignKey to GraphVersion)
  - [x] status (CharField, choices: pending, running, paused, succeeded, failed, canceled)
  - [x] started_at (DateTimeField, null=True)
  - [x] ended_at (DateTimeField, null=True)
  - [x] input_json (JSONField, blank=True)
  - [x] output_json (JSONField, blank=True, null=True)
  - [x] error_message (TextField, blank=True)
- [x] 3.3.2 Create migrations for run models

---

## 4. CRUD APIs

### 4.1 Graph APIs

- [x] 4.1.1 Create Graph serializers
  - [x] GraphListSerializer (id, name, description, created_at, updated_at, latest_version)
  - [x] GraphDetailSerializer (includes versions list)
  - [x] GraphCreateSerializer (name, description)
  - [x] GraphUpdateSerializer (name, description)
- [x] 4.1.2 Create GraphVersion serializers
  - [x] GraphVersionListSerializer (id, version, created_at, checksum)
  - [x] GraphVersionDetailSerializer (includes full graph_json)
  - [x] GraphVersionCreateSerializer (graph_json)
- [x] 4.1.3 Create Graph viewsets
  - [x] GET /api/graphs/ - list user's graphs
  - [x] POST /api/graphs/ - create new graph
  - [x] GET /api/graphs/{id}/ - get graph details with versions
  - [x] PATCH /api/graphs/{id}/ - update graph name/description
  - [x] DELETE /api/graphs/{id}/ - delete graph and all versions
- [x] 4.1.4 Create GraphVersion viewsets
  - [x] GET /api/graphs/{graph_id}/versions/ - list versions
  - [x] POST /api/graphs/{graph_id}/versions/ - create new version (auto-increment version number)
  - [x] GET /api/graphs/{graph_id}/versions/{id}/ - get version with full graph_json
  - [x] GET /api/graphs/{graph_id}/versions/latest/ - get latest version
- [x] 4.1.5 Add graph validation
  - [x] Validate graph_json structure (has nodes, edges, metadata)
  - [x] Validate node types are recognized
  - [x] Validate edge references exist
  - [x] Generate checksum on save
- [x] 4.1.6 Write Graph API tests
  - [x] Test CRUD operations
  - [x] Test version auto-increment
  - [x] Test owner-scoped access
  - [x] Test graph_json validation

### 4.2 Prompt APIs

- [x] 4.2.1 Create PromptTemplate serializers
  - [x] PromptTemplateListSerializer (id, title, description, category, visibility, is_builtin)
  - [x] PromptTemplateDetailSerializer (includes content, variables_schema, version, license)
  - [x] PromptTemplateCreateSerializer (title, description, category, content, variables_schema)
  - [x] PromptTemplateUpdateSerializer (title, description, content, variables_schema)
  - [x] PromptTemplatePublishSerializer (visibility, license)
- [x] 4.2.2 Create PromptTemplate viewsets
  - [x] GET /api/prompts/ - list prompts (user's + public built-in)
  - [x] POST /api/prompts/ - create new prompt (private by default)
  - [x] GET /api/prompts/{id}/ - get prompt details
  - [x] PATCH /api/prompts/{id}/ - update prompt (owner only)
  - [x] DELETE /api/prompts/{id}/ - delete prompt (owner only, not built-in)
  - [x] POST /api/prompts/{id}/clone/ - clone prompt to user's library
  - [x] POST /api/prompts/{id}/publish/ - make prompt public (owner only)
- [x] 4.2.3 Add prompt filtering
  - [x] Filter by category
  - [x] Filter by visibility (public/private/all)
  - [x] Filter by owner (mine/builtin/all)
  - [x] Search by title/description
- [x] 4.2.4 Write Prompt API tests
  - [x] Test CRUD operations
  - [x] Test clone functionality
  - [x] Test publish functionality
  - [x] Test filtering and search
  - [x] Test built-in prompts are read-only

---

## 5. Seed Data

- [x] 5.1 Create data migration for built-in prompts
- [x] 5.2 Create 10 built-in prompt templates:

### Research Category
- [x] 5.2.1 **Research Summary** - Summarize research findings on a topic
- [x] 5.2.2 **Competitive Analysis** - Analyze competitors for a product/service

### Summarization Category
- [x] 5.2.3 **Document Summary** - Summarize a long document into key points
- [x] 5.2.4 **Meeting Notes** - Convert meeting transcript to structured notes

### Email Category
- [x] 5.2.5 **Professional Email** - Draft a professional email from key points
- [x] 5.2.6 **Follow-up Email** - Generate follow-up email after a meeting

### Extraction Category
- [x] 5.2.7 **Entity Extraction** - Extract named entities from text
- [x] 5.2.8 **Data Parser** - Parse unstructured text into structured JSON

### Reasoning Category
- [x] 5.2.9 **Decision Analysis** - Analyze pros/cons for a decision
- [x] 5.2.10 **Step-by-Step Solver** - Break down a problem into steps

- [x] 5.3 Each prompt should include:
  - [x] Clear title and description
  - [x] Well-crafted prompt content with {{variable}} placeholders
  - [x] variables_schema defining expected inputs
  - [x] Appropriate category
  - [x] visibility='public', owner=None

---

## 6. Frontend - Authentication Pages

- [x] 6.1 Set up frontend authentication infrastructure
  - [x] Install axios for API calls
  - [x] Create API client with base URL and interceptors
  - [x] Create auth context/store for user state
  - [x] Create useAuth hook
  - [x] Set up JWT token storage (httpOnly cookies or localStorage)
  - [x] Add token refresh logic
- [x] 6.2 Create Login page (/login)
  - [x] Email and password form
  - [x] Form validation
  - [x] Error handling and display
  - [x] Redirect to /graphs on success
  - [x] Link to register page
- [x] 6.3 Create Register page (/register)
  - [x] Email, password, confirm password form
  - [x] Form validation
  - [x] Error handling and display
  - [x] Redirect to /login on success
  - [x] Link to login page
- [x] 6.4 Create protected route wrapper
  - [x] Redirect to /login if not authenticated
  - [x] Show loading state while checking auth
- [x] 6.5 Add logout functionality
  - [x] Logout button in header/nav
  - [x] Clear tokens and redirect to /login

---

## 7. Frontend - Graph List Page

- [x] 7.1 Create Graphs list page (/graphs)
  - [x] Fetch and display user's graphs
  - [x] Show graph name, description, last updated, version count
  - [x] Empty state for no graphs
  - [x] Loading state
  - [x] Error handling
- [x] 7.2 Create New Graph modal/form
  - [x] Name and description inputs
  - [x] Create graph via API
  - [x] Redirect to graph editor (placeholder for Phase 2)
- [x] 7.3 Add graph actions
  - [x] Edit graph metadata
  - [x] Delete graph (with confirmation)
  - [x] View graph versions
- [x] 7.4 Create basic navigation
  - [x] Header with logo, nav links (Graphs, Prompts), user menu
  - [x] User menu with logout option

---

## 8. Frontend - Prompt Library Page

- [x] 8.1 Create Prompts list page (/prompts)
  - [x] Fetch and display prompts (built-in + user's)
  - [x] Show title, description, category, visibility badge
  - [x] Differentiate built-in vs user prompts visually
  - [x] Empty state for no user prompts
  - [x] Loading state
  - [x] Error handling
- [x] 8.2 Add prompt filtering
  - [x] Filter tabs/dropdown by category
  - [x] Filter by ownership (All, Built-in, My Prompts)
  - [x] Search input for title/description
- [x] 8.3 Create Prompt detail modal/page
  - [x] Show full prompt content
  - [x] Show variables schema
  - [x] Show metadata (version, license, category)
  - [x] Clone button (for built-in prompts)
  - [x] Edit/Delete buttons (for user's prompts)
- [x] 8.4 Create New Prompt modal/form
  - [x] Title, description, category, content inputs
  - [x] Variables schema editor (simple JSON or form)
  - [x] Create prompt via API
- [x] 8.5 Add prompt actions
  - [x] Clone prompt to user's library
  - [x] Edit user prompt
  - [x] Delete user prompt (with confirmation)
  - [x] Publish prompt (make public)

---

## 9. API URL Configuration

- [x] 9.1 Set up URL routing
  - [x] /api/auth/* - authentication endpoints
  - [x] /api/graphs/* - graph endpoints
  - [x] /api/prompts/* - prompt endpoints
  - [x] /api/runs/* - run endpoints (stub)
  - [x] /health - health check (existing)
- [x] 9.2 Add API versioning (optional)
  - [x] Consider /api/v1/* prefix for future compatibility
- [x] 9.3 Configure DRF browsable API
  - [x] Enable for development
  - [x] Disable for production

---

## 10. Testing & Quality

- [x] 10.1 Set up pytest for Django
  - [x] Add pytest-django to requirements.txt
  - [x] Configure pytest.ini
  - [x] Create conftest.py with fixtures
- [x] 10.2 Create test fixtures
  - [x] User factory
  - [x] Graph/GraphVersion factory
  - [x] PromptTemplate factory
- [x] 10.3 Write model tests
  - [x] Test model constraints
  - [x] Test model methods
  - [x] Test managers
- [x] 10.4 Write API integration tests
  - [x] Test all endpoints
  - [x] Test permissions
  - [x] Test error cases
- [x] 10.5 Add API documentation
  - [x] Install drf-spectacular or drf-yasg
  - [x] Generate OpenAPI schema
  - [x] Serve Swagger UI at /api/docs/

---

## 11. Docker & DevOps Updates

- [x] 11.1 Update backend Dockerfile
  - [x] Ensure all new dependencies are installed
  - [x] Add migration command to entrypoint
- [x] 11.2 Update docker-compose.yml
  - [x] Add volume for static files
  - [x] Ensure proper startup order
- [x] 11.3 Create database initialization script
  - [x] Run migrations on startup
  - [x] Create superuser if not exists
  - [x] Seed built-in prompts if not exists
- [x] 11.4 Update dev script
  - [x] Add `./dev migrate` command
  - [x] Add `./dev shell` command for Django shell
  - [x] Add `./dev test` command for running tests

---

## 12. Final Verification

- [x] 12.1 End-to-end testing
  - [x] Register new user
  - [x] Login with new user
  - [x] View prompt library (see 10 built-in prompts)
  - [x] Clone a prompt
  - [x] Create new graph
  - [x] Create graph version with sample JSON
  - [x] View graph list
  - [x] Logout and login again
- [x] 12.2 Update documentation
  - [x] Update CLAUDE.md with new commands
  - [x] Update README.md if needed
- [x] 12.3 Clean up
  - [x] Remove any debug code
  - [x] Ensure no sensitive data in commits
  - [x] Verify all tests pass

---

## Summary Checklist

| Section | Tasks | Status |
|---------|-------|--------|
| 1. Django Setup | 4 | ✅ |
| 2. Authentication | 7 | ✅ |
| 3. Data Models | 10 | ✅ |
| 4. CRUD APIs | 12 | ✅ |
| 5. Seed Data | 13 | ✅ |
| 6. Frontend Auth | 5 | ✅ |
| 7. Frontend Graphs | 4 | ✅ |
| 8. Frontend Prompts | 5 | ✅ |
| 9. URL Config | 3 | ✅ |
| 10. Testing | 5 | ✅ |
| 11. Docker/DevOps | 4 | ✅ |
| 12. Verification | 3 | ✅ |

**Total: ~75 tasks**
