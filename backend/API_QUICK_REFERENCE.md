# ForgeGraph API Quick Reference

## Base URL
```
http://localhost:8000/api
```

## Authentication
Most endpoints require JWT authentication. Include the access token in the Authorization header:
```
Authorization: Bearer <your_access_token>
```

This API uses a double JWT approach:
- **Access token**: returned in JSON (short-lived) and sent via `Authorization: Bearer ...`
- **Refresh token**: stored in a **HttpOnly cookie** (rotated) and used by `POST /api/auth/refresh`

## Response Format

All responses follow this standard format:

**Success:**
```json
{
  "data": { /* response payload */ },
  "meta": {
    "requestId": "uuid",
    "timestamp": "ISO-8601"
  }
}
```

**Error:**
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable message",
    "details": [/* optional field-level errors */]
  },
  "meta": {
    "requestId": "uuid",
    "timestamp": "ISO-8601"
  }
}
```

---

## Graph APIs

### List Graphs
```http
GET /api/graphs/
```

**Response:**
```json
{
  "data": [
    {
      "id": "uuid",
      "name": "My Workflow",
      "description": "Description",
      "created_at": "2024-01-15T10:00:00Z",
      "updated_at": "2024-01-15T10:30:00Z",
      "version_count": 3,
      "latest_version": 3
    }
  ],
  "meta": { ... }
}
```

### Create Graph
```http
POST /api/graphs/
Content-Type: application/json

{
  "name": "New Workflow",
  "description": "Optional description"
}
```

**Response:** `201 Created` with graph object

### Get Graph Details
```http
GET /api/graphs/{graph_id}
```

**Response:**
```json
{
  "data": {
    "id": "uuid",
    "owner_id": "uuid",
    "name": "My Workflow",
    "description": "Description",
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:30:00Z",
    "versions": [
      {
        "id": "uuid",
        "version": 2,
        "checksum": "sha256...",
        "created_at": "2024-01-15T10:30:00Z"
      },
      {
        "id": "uuid",
        "version": 1,
        "checksum": "sha256...",
        "created_at": "2024-01-15T10:00:00Z"
      }
    ]
  },
  "meta": { ... }
}
```

### Update Graph
```http
PATCH /api/graphs/{graph_id}
Content-Type: application/json

{
  "name": "Updated Name",
  "description": "Updated description"
}
```

**Response:** `200 OK` with updated graph

### Delete Graph
```http
DELETE /api/graphs/{graph_id}
```

**Response:** `204 No Content`

---

## Graph Version APIs

### List Versions
```http
GET /api/graphs/{graph_id}/versions
```

**Response:**
```json
{
  "data": [
    {
      "id": "uuid",
      "version": 2,
      "checksum": "sha256...",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "meta": { ... }
}
```

### Create Version
```http
POST /api/graphs/{graph_id}/versions
Content-Type: application/json

{
  "graph_json": {
    "nodes": [
      {
        "id": "node1",
        "type": "prompt",
        "name": "Start Node",
        "config": { ... }
      }
    ],
    "edges": [
      {
        "id": "edge1",
        "from": "node1",
        "to": "node2"
      }
    ]
  }
}
```

**Response:** `201 Created` with version object including full `graph_json`

**Validation:**
- Checks for required fields (nodes, edges)
- Validates node structure (id, type, name)
- Validates node types against allowed types
- Validates edge references
- Checks for cycles (DAG validation)
- Computes SHA256 checksum

### Get Specific Version
```http
GET /api/graphs/{graph_id}/versions/{version_id}
```

**Response:** Version object with full `graph_json`

### Get Latest Version
```http
GET /api/graphs/{graph_id}/versions/latest
```

**Response:** Most recent version with full `graph_json`

---

## Prompt APIs

### List Prompts
```http
GET /api/prompts/
GET /api/prompts/?category=research
GET /api/prompts/?ownership=mine
GET /api/prompts/?search=email
```

**Query Parameters:**
- `category` - Filter by category (research, summarization, email, extraction, reasoning, other)
- `ownership` - Filter by ownership (all, mine, builtin)
- `search` - Search in title and description

**Response:**
```json
{
  "data": [
    {
      "id": "uuid",
      "title": "Research Assistant",
      "description": "Helps with research tasks",
      "category": "research",
      "visibility": "public",
      "is_builtin": false,
      "created_at": "2024-01-15T10:00:00Z"
    }
  ],
  "meta": { ... }
}
```

### Create Prompt
```http
POST /api/prompts/
Content-Type: application/json

{
  "title": "Email Draft Helper",
  "description": "Helps draft professional emails",
  "category": "email",
  "content": "You are an assistant that helps write professional emails...",
  "variables_schema": {
    "recipient": { "type": "string" },
    "subject": { "type": "string" }
  }
}
```

**Response:** `201 Created` with prompt object (visibility defaults to "private")

### Get Prompt Details
```http
GET /api/prompts/{prompt_id}
```

**Response:**
```json
{
  "data": {
    "id": "uuid",
    "owner_id": "uuid",
    "title": "Email Draft Helper",
    "description": "Helps draft professional emails",
    "category": "email",
    "content": "You are an assistant...",
    "variables_schema": { ... },
    "version": "1.0.0",
    "license": "MIT",
    "visibility": "private",
    "is_builtin": false,
    "created_at": "2024-01-15T10:00:00Z",
    "updated_at": "2024-01-15T10:00:00Z"
  },
  "meta": { ... }
}
```

### Update Prompt
```http
PATCH /api/prompts/{prompt_id}
Content-Type: application/json

{
  "title": "Updated Title",
  "content": "Updated content",
  "variables_schema": { ... }
}
```

**Response:** `200 OK` with updated prompt

**Note:** Only the owner can update prompts

### Delete Prompt
```http
DELETE /api/prompts/{prompt_id}
```

**Response:** `204 No Content`

**Note:** Only the owner can delete prompts. Built-in prompts cannot be deleted.

### Clone Prompt
```http
POST /api/prompts/{prompt_id}/clone
```

**Response:** `201 Created` with cloned prompt

**Access:**
- Can clone own prompts
- Can clone public prompts from other users
- Can clone built-in prompts (owner=null)
- Cannot clone private prompts from other users

**Behavior:**
- Creates a private copy for the current user
- Title gets "(Copy)" suffix
- All content and variables_schema are duplicated

### Publish Prompt
```http
POST /api/prompts/{prompt_id}/publish
Content-Type: application/json

{
  "license": "Apache-2.0"
}
```

**Response:** `200 OK` with updated prompt (visibility now "public")

**Note:**
- Only the owner can publish prompts
- License defaults to "MIT" if not specified
- Once public, the prompt can be viewed and cloned by all users

---

## Error Codes

| Code | Description | HTTP Status |
|------|-------------|-------------|
| `VALIDATION_ERROR` | Invalid input fields | 400 |
| `GRAPH_VALIDATION_ERROR` | Graph structure validation failed | 400 |
| `NOT_FOUND` | Resource not found or unauthorized | 404 |

## Node Types (for Graph JSON)

Valid node types for graph validation:
- `prompt` - LLM prompt node
- `http` - HTTP API call node
- `transform` - Data transformation node
- `branch` - Conditional branching node
- `merge` - Merge parallel branches node
- `human_gate` - Human approval gate node
- `output` - Output node

## Example: Complete Graph JSON

```json
{
  "nodes": [
    {
      "id": "start",
      "type": "prompt",
      "name": "Research Query",
      "config": {
        "prompt_template_id": "uuid",
        "variables": {
          "topic": "AI agents"
        }
      }
    },
    {
      "id": "search",
      "type": "http",
      "name": "Web Search",
      "config": {
        "method": "GET",
        "url": "https://api.search.com/search",
        "headers": {
          "Authorization": "Bearer token"
        }
      }
    },
    {
      "id": "end",
      "type": "output",
      "name": "Final Result",
      "config": {
        "output_key": "result"
      }
    }
  ],
  "edges": [
    {
      "id": "e1",
      "from": "start",
      "to": "search"
    },
    {
      "id": "e2",
      "from": "search",
      "to": "end"
    }
  ]
}
```

---

## Testing with cURL

### Get Access Token
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"email": "user@example.com", "password": "password"}'
```

### Refresh Access Token
```bash
curl -X POST http://localhost:8000/api/auth/refresh \
  -b cookies.txt \
  -c cookies.txt
```

### Logout
```bash
curl -X POST http://localhost:8000/api/auth/logout \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -b cookies.txt
```

### List Graphs
```bash
curl http://localhost:8000/api/graphs/ \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Create Graph
```bash
curl -X POST http://localhost:8000/api/graphs/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Workflow", "description": "Test workflow"}'
```

### Create Graph Version
```bash
curl -X POST http://localhost:8000/api/graphs/GRAPH_ID/versions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"graph_json": {"nodes": [], "edges": []}}'
```

---

## Rate Limiting (Future)

Rate limit headers will be included in responses:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1640000000
```

When rate limited:
```
HTTP 429 Too Many Requests
Retry-After: 3600

{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again in 1 hour."
  },
  "meta": { ... }
}
```

---

## Support

For issues or questions:
1. Check this documentation
2. Review the API tests in `backend/tests/integration/adapters/`
3. See `API_IMPLEMENTATION_SUMMARY.md` for detailed information
