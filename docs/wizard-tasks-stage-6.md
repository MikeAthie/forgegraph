# Stage 6: Backend & Engine Updates

## Objective
Update the backend API and Go engine to support new wizard features including enhanced validation and node schemas. (Quick templates are hardcoded in frontend only.)

## Prerequisites
- Stage 1 & 3 complete (foundation and validation)
- Understanding of existing backend/engine architecture

---

## Task List

### 6.1 Enhanced Graph Validation Rules
**File:** `backend/domain/services/graph_validator.py`

- [ ] Add explicit Start edge validation:
  ```python
  def _validate_start_edges(self, edges: list) -> list:
      start_edges = [e for e in edges if e.get('from') == 'START']
      if not start_edges:
          return [{'type': 'no_start_node',
                   'message': 'Graph must have at least one start edge',
                   'suggestion': 'Add an edge from START to your first node'}]
      return []
  ```
- [ ] Add explicit Output node validation (already exists, verify)
- [ ] Add disconnected node detection:
  ```python
  def _validate_connectivity(self, nodes, edges) -> list:
      # Find nodes with no incoming AND no outgoing edges
      # Exclude START/END sentinels
  ```
- [ ] Add node config validation (required fields per type)
- [ ] Return structured errors with suggestions

### 6.2 Create Node Schema Definitions
**File:** `backend/domain/value_objects/node_schemas.py`

- [ ] Define JSON Schema for each node type's config:
  ```python
  PROMPT_NODE_SCHEMA = {
      "type": "object",
      "properties": {
          "prompt": {"type": "string", "minLength": 1},
          "system_prompt": {"type": "string"},
          "model": {"type": "string"},
          "temperature": {"type": "number", "minimum": 0, "maximum": 2},
          # Agent fields
          "role": {"type": "string"},
          "job_description": {"type": "string"},
          "examples": {"type": "array", "items": {...}},
          "notes": {"type": "string"},
      },
      "required": ["prompt"]
  }
  ```
- [ ] Create schemas for all 10 node types
- [ ] Export schema registry

### 6.3 Add Node Config Validation to GraphValidator
**File:** `backend/domain/services/graph_validator.py`

- [ ] Import node schemas
- [ ] Add config validation step:
  ```python
  def _validate_node_configs(self, nodes: list) -> list:
      errors = []
      for node in nodes:
          schema = get_schema_for_type(node['type'])
          validation_errors = validate_json_schema(node.get('config', {}), schema)
          if validation_errors:
              errors.append({
                  'type': 'invalid_node_config',
                  'node_id': node['id'],
                  'errors': validation_errors
              })
      return errors
  ```
- [ ] Make config validation optional (strict mode flag)

### 6.4 Add Validation Endpoint
**File:** `backend/adapters/api/graphs.py`

- [ ] Add POST `/api/graphs/validate` endpoint:
  ```python
  @api_view(['POST'])
  def validate_graph(request):
      graph_json = request.data.get('graph_json')
      strict = request.data.get('strict', False)

      validator = GraphValidator()
      errors = validator.validate(graph_json, strict=strict)

      return Response({
          'valid': len([e for e in errors if e['type'] != 'warning']) == 0,
          'errors': errors,
          'warnings': [e for e in errors if e['type'] == 'warning']
      })
  ```
- [ ] Support strict mode (config validation)
- [ ] Return structured error response

### 6.5 Update Graph Metadata Schema
**File:** `backend/domain/entities/graph.py`

- [ ] Extend metadata to include:
  ```python
  metadata = {
      # Existing
      'input_schema': {...},
      'output_schema': {...},
      # New
      'agent_config': {
          'name': str,
          'role': str,
          'objective': str,
          'personality': list[str]
      },
      'edge_types': {
          'edge_id': 'data_type'
      }
  }
  ```
- [ ] Preserve backward compatibility

### 6.6 Engine: Add Data Type to Edge
**File:** `engine/domain/entity/graph.go`

- [ ] Update Edge struct:
  ```go
  type Edge struct {
      ID        string `json:"id"`
      From      string `json:"from"`
      To        string `json:"to"`
      Condition string `json:"condition,omitempty"`
      Label     string `json:"label,omitempty"`
      DataType  string `json:"data_type,omitempty"`  // New
  }
  ```
- [ ] Parse data_type from JSON
- [ ] No execution behavior change (metadata only)

### 6.7 Engine: Log Data Types During Execution
**File:** `engine/application/usecase/scheduler.go`

- [ ] Add debug logging for data types:
  ```go
  func (s *Scheduler) executeNode(...) {
      // Log incoming data types
      for _, edge := range incomingEdges {
          if edge.DataType != "" {
              s.logger.Debug("Node %s receiving %s data from %s",
                  nodeID, edge.DataType, edge.From)
          }
      }
      // ... existing execution
  }
  ```
- [ ] Useful for debugging type mismatches

### 6.8 Engine: Validate Required Node Config
**File:** `engine/domain/service/graph_validator.go`

- [ ] Add basic config validation:
  ```go
  func (v *GraphValidator) validateNodeConfigs(nodes []Node) []error {
      var errors []error
      for _, node := range nodes {
          switch node.Type {
          case "prompt":
              if node.Config["prompt"] == nil {
                  errors = append(errors, fmt.Errorf(
                      "node %s: prompt config required", node.ID))
              }
          // ... other types
          }
      }
      return errors
  }
  ```
- [ ] Fail fast on missing required config

### 6.9 Add Agent Metadata to Run
**File:** `backend/domain/entities/run.py`

- [ ] Include agent config in run metadata:
  ```python
  run_metadata = {
      'agent_name': graph.metadata.get('agent_config', {}).get('name'),
      'agent_role': graph.metadata.get('agent_config', {}).get('role'),
      # ... for display in run history
  }
  ```
- [ ] Store in Run entity for display purposes

### 6.10 API Tests for Validation Endpoint
**File:** `backend/tests/integration/adapters/test_validation_api.py`

- [ ] Test valid graph returns no errors
- [ ] Test missing start edge returns error
- [ ] Test missing output node returns error
- [ ] Test disconnected node returns warning
- [ ] Test invalid node config in strict mode
- [ ] Test error response format

### 6.11 Engine Tests for Type Metadata
**File:** `engine/test/graph_types_test.go`

- [ ] Test Edge DataType parsing
- [ ] Test Graph with edge types
- [ ] Test execution with type metadata (no behavior change)

---

## Acceptance Criteria

1. `/api/graphs/validate` endpoint returns structured errors
2. Validation includes start edge, output node, connectivity checks
3. Node config validation works in strict mode
4. Engine parses edge data types without errors
5. Engine logs data types during execution (debug)
6. All API tests passing
7. Backward compatible with existing graphs

## Dependencies

- Stage 1 & 3 complete (foundation and frontend validation)
- Database access
- Existing validation infrastructure

## Output

- Enhanced GraphValidator with new rules
- Node schema definitions
- Validation API endpoint
- Engine data type support
- Comprehensive API tests
