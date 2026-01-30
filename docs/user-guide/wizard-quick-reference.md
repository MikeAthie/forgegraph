# Agent Wizard - Quick Reference

One-page reference for the ForgeGraph Agent Creation Wizard.

---

## Keyboard Shortcuts

| Action | Windows/Linux | Mac |
|--------|---------------|-----|
| Open Wizard | `Ctrl+Shift+W` | `Cmd+Shift+W` |
| Save | `Ctrl+S` | `Cmd+S` |
| Undo | `Ctrl+Z` | `Cmd+Z` |
| Redo | `Ctrl+Y` | `Cmd+Shift+Z` |
| Delete | `Delete` | `Backspace` |
| Duplicate | `Ctrl+D` | `Cmd+D` |
| Select All | `Ctrl+A` | `Cmd+A` |
| Copy | `Ctrl+C` | `Cmd+C` |
| Paste | `Ctrl+V` | `Cmd+V` |
| Search Nodes | `Ctrl+Shift+F` | `Cmd+Shift+F` |

---

## Node Types

| Type | Icon | Purpose | Required Fields |
|------|------|---------|-----------------|
| **Prompt** | M | LLM call with prompt template | prompt_id, model |
| **HTTP** | H | External API request | url, method |
| **Transform** | T | Data transformation | expression |
| **Branch** | B | Conditional routing | condition |
| **Merge** | M | Join parallel branches | strategy |
| **Tool** | TL | Call registered tool | tool_name |
| **Subgraph** | SG | Run nested graph | graph_id |
| **Memory** | S | Store/retrieve state | action, key |
| **Human Gate** | G | Pause for approval | prompt |
| **Output** | O | Define final output | output_mapping |
| **Note** | N | Canvas annotation | (none) |

---

## Data Types

| Type | Description | Example |
|------|-------------|---------|
| `text` | Plain text string | `"Hello, world"` |
| `json` | Structured JSON object | `{"key": "value"}` |
| `number` | Numeric value | `42`, `3.14` |
| `boolean` | True/false value | `true`, `false` |
| `array` | List of items | `[1, 2, 3]` |
| `any` | Accepts any type | (flexible) |

---

## Validation Errors

| Code | Message | Quick Fix |
|------|---------|-----------|
| `NO_START` | Graph needs a start node | Click "Add Start" indicator |
| `NO_OUTPUT` | Graph needs an output node | Add Output node |
| `DISCONNECTED` | Node not connected | Connect or delete node |
| `CYCLE` | Circular dependency detected | Remove cyclic edge |
| `EMPTY` | Graph is empty | Add at least one node |

---

## State Path Examples

Access data from your workflow using state paths:

```
node.prompt_1.output          # Output from prompt node
node.http_1.output.data       # Nested HTTP response data
node.transform_1.output       # Transform result
input.userId                  # Original graph input
memory.user_preferences       # Stored memory value
```

---

## Quick Node Presets

### AI
- **Simple Chat** - Basic LLM conversation
- **RAG Query** - Retrieval-augmented generation

### Integration
- **REST API Call** - HTTP GET with JSON
- **Webhook Handler** - Process incoming data

### Logic
- **Conditional Router** - Branch on conditions
- **Data Transformer** - Common transforms

---

## Wizard Steps (In Order)

1. **Start** - Mark entry point (trigger node)
2. **Role** - Configure main prompt/LLM
3. **Tools** - Add HTTP, transforms, etc.
4. **Memory** - Configure persistence (optional)
5. **Output** - Define return values
6. **Review** - Validate and save

---

## Graph Structure Indicators

| Indicator | Meaning |
|-----------|---------|
| **Start** badge | Node is the entry point |
| **End** badge | Node is an exit point |
| **Yellow border** | Node has validation warning |
| **Red border** | Node has validation error |
| **Asterisk (*)** | Graph has unsaved changes |

---

## Common Patterns

### Simple Request-Response
```
[Start/Prompt] → [Output]
```

### API Integration
```
[Prompt] → [HTTP] → [Transform] → [Output]
```

### Conditional Flow
```
[Prompt] → [Branch] → [Path A] → [Merge] → [Output]
                   ↘ [Path B] ↗
```

### With Memory
```
[Memory GET] → [Prompt] → [Memory SET] → [Output]
```

---

## Tips

- **Always save** before running (Ctrl+S)
- **Use Transform nodes** to format data between steps
- **Check the status bar** for validation errors
- **Hover over edges** to see data types
- **Click node badges** to toggle start/end status
