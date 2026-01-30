# Stage 4: Data Flow & Type Propagation

## Objective
Track and display data types flowing between nodes, enabling type compatibility checking and helping users understand what data each node produces and consumes.

## Prerequisites
- Stage 1-3 complete
- Understanding of graph execution flow
- Understanding of node input/output patterns

---

## Task List

### 4.1 Define Data Type System
**File:** `frontend/lib/data-types.ts`

- [ ] Define core data types enum:
  ```typescript
  enum DataType {
    TEXT = 'text',        // Plain string
    JSON = 'json',        // Structured JSON object
    ARRAY = 'array',      // List/array of items
    NUMBER = 'number',    // Numeric value
    BOOLEAN = 'boolean',  // True/false
    IMAGE = 'image',      // Image binary/URL
    FILE = 'file',        // File binary/path
    ANY = 'any',          // Accepts anything
    VOID = 'void',        // No output
  }
  ```
- [ ] Define DataTypeSchema interface for detailed schemas:
  ```typescript
  interface DataTypeSchema {
    type: DataType
    schema?: JSONSchema   // Optional detailed JSON Schema
    description?: string  // Human-readable description
    example?: any         // Example value
  }
  ```
- [ ] Create type compatibility matrix

### 4.2 Define Node Type Signatures
**File:** `frontend/lib/node-type-signatures.ts`

- [ ] Define input/output signatures for each node type:
  ```typescript
  const nodeSignatures: Record<NodeType, NodeSignature> = {
    prompt: {
      inputs: [{ name: 'context', type: DataType.JSON, required: false }],
      outputs: [{ name: 'response', type: DataType.TEXT }]
    },
    http: {
      inputs: [{ name: 'body', type: DataType.JSON, required: false }],
      outputs: [{ name: 'response', type: DataType.JSON }]
    },
    transform: {
      inputs: [{ name: 'input', type: DataType.ANY }],
      outputs: [{ name: 'output', type: DataType.ANY }]  // Dynamic
    },
    branch: {
      inputs: [{ name: 'value', type: DataType.ANY }],
      outputs: []  // Control flow only
    },
    merge: {
      inputs: [{ name: 'sources', type: DataType.ANY, multiple: true }],
      outputs: [{ name: 'merged', type: DataType.JSON }]
    },
    // ... other types
  }
  ```
- [ ] Export getNodeSignature utility function

### 4.3 Create Type Inference Engine
**File:** `frontend/lib/type-inference.ts`

- [ ] Implement `inferOutputType(node)` function
  - Use node signature as base
  - Override with explicit outputType in config if set
  - For Transform nodes, try to infer from expression
- [ ] Implement `inferInputType(node, inputName)` function
  - Look at incoming edges
  - Collect output types from source nodes
- [ ] Implement `getAvailableData(nodeId, nodes, edges)` function
  - Return all data available to a node from predecessors
  - Include data type and source node info

### 4.4 Create Type Compatibility Checker
**File:** `frontend/lib/type-compatibility.ts`

- [ ] Implement `areTypesCompatible(source, target)` function
- [ ] Compatibility rules:
  - `ANY` accepts everything
  - `JSON` accepts `TEXT` (as JSON string)
  - `ARRAY` accepts `JSON` (if array schema)
  - Exact type matches always compatible
  - Everything converts to `TEXT` (stringification)
- [ ] Return compatibility result with reason if incompatible

### 4.5 Update Edge Data Model
**File:** `frontend/lib/graph-types.ts`

- [ ] Add type metadata to Edge interface:
  ```typescript
  interface Edge {
    // ... existing fields
    dataType?: DataType
    dataSchema?: DataTypeSchema
    isTypeInferred?: boolean
  }
  ```
- [ ] Add utility to compute edge data type from connected nodes

### 4.6 Create DataTypeIndicator Component
**File:** `frontend/components/graph-editor/DataTypeIndicator.tsx`

- [ ] Create badge component showing data type
- [ ] Design:
  - Small pill/badge with type icon and label
  - Color-coded by type (e.g., green for JSON, blue for TEXT)
  - Click to see detailed schema
- [ ] Show on edges between nodes
- [ ] Position at edge midpoint or near target handle

### 4.7 Create DataTypeTooltip Component
**File:** `frontend/components/graph-editor/DataTypeTooltip.tsx`

- [ ] Create detailed tooltip for data types
- [ ] Show:
  - Type name and icon
  - Description
  - JSON Schema (if available)
  - Example value
  - Source node name
- [ ] Trigger on hover over DataTypeIndicator

### 4.8 Create TypeMismatchWarning Component
**File:** `frontend/components/graph-editor/TypeMismatchWarning.tsx`

- [ ] Create warning indicator for type mismatches
- [ ] Design:
  - Yellow/orange warning icon on edge
  - Tooltip explaining the mismatch
  - "Source outputs X, but target expects Y"
- [ ] Provide suggestion for resolution

### 4.9 Implement Custom Edge with Type Display
**File:** `frontend/components/graph-editor/edges/TypedEdge.tsx`

- [ ] Create custom React Flow edge component
- [ ] Render:
  - Normal edge line
  - DataTypeIndicator at midpoint (if type known)
  - TypeMismatchWarning if incompatible
  - Animated flow direction indicator (optional)
- [ ] Handle edge selection
- [ ] Update existing edge rendering to use TypedEdge

### 4.10 Update GraphNode Output Handles
**File:** `frontend/components/graph-editor/nodes/GraphNode.tsx`

- [ ] Add output type indicator near output handle
- [ ] Show small type badge (T for text, {} for JSON, etc.)
- [ ] Color-code handle by output type
- [ ] Tooltip shows full output type info

### 4.11 Update NodeInspector with Type Info
**File:** `frontend/components/graph-editor/NodeInspector.tsx`

- [ ] Add "Input Types" section showing incoming data
- [ ] Add "Output Type" section showing what node produces
- [ ] Allow manual output type override in config
- [ ] Show type compatibility warnings for connected edges

### 4.12 Create Available Data Panel
**File:** `frontend/components/graph-editor/AvailableDataPanel.tsx`

- [ ] Create panel showing data available to selected node
- [ ] List all predecessor nodes with their outputs:
  ```
  Available Data:
  - node_1.output (text): "User's prompt response"
  - node_2.output (json): { status: "ok", data: {...} }
  - input.userId (text): "User ID from graph input"
  ```
- [ ] Allow clicking to insert reference in form fields
- [ ] Filter/search available data

### 4.13 Integrate Type Checking with Validation
**File:** `frontend/lib/graph-validator.ts`

- [ ] Add type mismatch detection to validateGraph:
  ```typescript
  for (const edge of edges) {
    const sourceType = inferOutputType(sourceNode)
    const targetType = inferInputType(targetNode)
    if (!areTypesCompatible(sourceType, targetType)) {
      warnings.push({ code: 'TYPE_MISMATCH', ... })
    }
  }
  ```
- [ ] Return type mismatches as warnings (not errors)
- [ ] Include suggested conversions

### 4.14 Update Graph Conversion for Type Metadata
**File:** `frontend/lib/graph-conversion.ts`

- [ ] Preserve data type metadata when converting:
  - ReactFlow → GraphJSON: Include edge data types
  - GraphJSON → ReactFlow: Restore edge data types
- [ ] Store inferred types in editor_state for persistence
- [ ] Recompute types on load if not stored

### 4.15 Backend: Store Type Metadata
**File:** `backend/domain/entities/graph.py`

- [ ] Update GraphVersion to support edge type metadata
- [ ] Ensure type metadata preserved in graph_json
- [ ] No validation changes (types are advisory)

### 4.16 Engine: Propagate Type Info (Metadata Only)
**File:** `engine/domain/entity/graph.go`

- [ ] Add DataType field to Edge struct (optional)
- [ ] Parse type metadata from graph JSON
- [ ] Log type info during execution (debugging)
- [ ] No execution behavior changes (types are UI-only)

### 4.17 Unit Tests for Type System
**Files:** `frontend/__tests__/lib/`

- [ ] Test data type compatibility rules
- [ ] Test type inference for each node type
- [ ] Test available data computation
- [ ] Test edge type determination

### 4.18 Component Tests for Type Display
**Files:** `frontend/__tests__/components/graph-editor/`

- [ ] Test DataTypeIndicator rendering
- [ ] Test TypedEdge with different types
- [ ] Test TypeMismatchWarning display
- [ ] Test AvailableDataPanel content

---

## Acceptance Criteria

1. Each edge shows data type indicator (badge) at midpoint
2. Data type badges are color-coded by type
3. Hovering type badge shows detailed tooltip with schema
4. Type mismatches show yellow warning on edge
5. NodeInspector shows input/output types
6. Available Data panel shows all accessible data for selected node
7. Type mismatches appear as warnings in validation
8. Types persist when saving/loading graphs
9. Manual type override possible in node config
10. Types correctly inferred for all node types

## Dependencies

- Stage 1-3 complete
- Understanding of data flow patterns
- React Flow custom edge support

## Output

- Data type system with compatibility rules
- Type inference engine
- DataTypeIndicator and TypedEdge components
- Type mismatch warnings in validation
- Available Data panel
- Type metadata persistence
