# Agent Creation Wizard - User Guide

The Agent Creation Wizard guides you through building AI agent workflows step by step, ensuring best practices and valid graph structure.

## Table of Contents

- [Overview](#overview)
- [When to Use the Wizard](#when-to-use-the-wizard)
- [Starting the Wizard](#starting-the-wizard)
- [Wizard Steps](#wizard-steps)
- [Quick Node Presets](#quick-node-presets)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Troubleshooting](#troubleshooting)

---

## Overview

The Agent Creation Wizard is a guided interface for creating AI agent workflows in ForgeGraph. It walks you through the essential steps of building a valid, runnable agent graph:

1. **Start Node** - Define the entry point
2. **Agent Role** - Configure the main prompt/LLM behavior
3. **Tools** - Add capabilities like HTTP calls, transforms, etc.
4. **Memory** - Configure persistent state (optional)
5. **Output** - Define what the agent returns
6. **Review** - Validate and save the graph

The wizard ensures your graph has all required components and follows best practices for agent design.

---

## When to Use the Wizard

**Use the wizard when:**
- Creating a new agent from scratch
- Learning how ForgeGraph agents work
- You want guided validation as you build
- Building a standard request-response agent

**Use manual mode when:**
- Editing an existing complex graph
- Building non-standard workflow patterns
- You're experienced with ForgeGraph

---

## Starting the Wizard

### From the Graph Editor

1. Create a new graph or open an existing empty graph
2. Click the **Wizard** button in the toolbar (or press `Ctrl+Shift+W`)
3. The wizard panel appears overlaying the canvas

### From an Empty Graph

When you create a new graph, the wizard automatically suggests starting to help you build a valid agent quickly.

---

## Wizard Steps

### Step 1: Add Start Node

Every agent needs an entry point. The Start node marks where execution begins.

**What happens:**
- A node is designated as the "trigger" (START entry)
- The graph validator recognizes this as the entry point
- Incoming data flows through this node first

**Tips:**
- Most agents use a Prompt node as the start
- You can change the start node later in the inspector

---

### Step 2: Define Agent Role

Configure the main behavior of your agent using a Prompt node.

**Fields:**
- **Prompt ID** - Select or create a prompt template
- **Model** - Choose the LLM (e.g., gpt-4, claude-3)
- **System Prompt** - Define the agent's role and behavior
- **Max Tokens** - Limit response length
- **Temperature** - Control randomness (0 = deterministic, 1 = creative)

**Example System Prompt:**
```
You are a helpful assistant that answers questions about our product.
Always be polite and concise. If you don't know something, say so.
```

---

### Step 3: Add Tools

Extend your agent's capabilities with tool nodes.

**Available Tools:**

| Tool | Description | Use Case |
|------|-------------|----------|
| **HTTP** | Make API calls | Fetch external data |
| **Transform** | Process data | Format, filter, combine |
| **Branch** | Conditional logic | Different paths based on conditions |
| **Merge** | Join branches | Combine parallel results |
| **Tool** | Call registered tools | External integrations |
| **Subgraph** | Nested workflows | Reuse other graphs |

**Adding Tools:**
1. Click on a tool type in the palette
2. Configure the tool in the dialog
3. The tool connects to your workflow automatically

---

### Step 4: Configure Memory (Optional)

Memory nodes allow your agent to persist and retrieve state across runs.

**Memory Actions:**
- **GET** - Retrieve a stored value
- **SET** - Store a value
- **DELETE** - Remove a stored value

**Use Cases:**
- User preferences
- Conversation history
- Cached API responses
- Session state

**Skip this step** if your agent doesn't need persistent memory.

---

### Step 5: Add Output

Define what your agent returns when execution completes.

**Output Configuration:**
- **Output Mapping** - Map state paths to output keys

**Example:**
```
result -> node.prompt_1.output
summary -> node.transform_1.output
```

**Tips:**
- Every valid graph needs at least one Output node
- The output mapping determines the final response structure

---

### Step 6: Review & Save

Before saving, the wizard validates your graph:

**Validation Checks:**
- Has a start node (trigger)
- Has at least one output node
- No disconnected nodes
- No circular dependencies

**If validation passes:**
- Click "Save" to create a version
- Your graph is ready to run

**If validation fails:**
- Review the error list
- Use quick fixes or manual corrections
- Re-validate before saving

---

## Quick Node Presets

Quick Node presets are pre-configured templates for common patterns.

### AI Presets
- **Simple Chat** - Basic prompt with chat completion
- **RAG Query** - Retrieval-augmented generation setup

### Integration Presets
- **REST API Call** - HTTP GET with JSON parsing
- **Webhook Handler** - Process incoming webhook data

### Logic Presets
- **Conditional Router** - Branch based on conditions
- **Data Transformer** - Common data transformations

**Using Presets:**
1. Click on a preset in the palette
2. Review the pre-filled configuration
3. Customize as needed
4. Add to your workflow

---

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Open/Close Wizard | `Ctrl+Shift+W` |
| Save Graph | `Ctrl+S` |
| Undo | `Ctrl+Z` |
| Redo | `Ctrl+Y` |
| Delete Node | `Delete` |
| Duplicate Node | `Ctrl+D` |
| Select All | `Ctrl+A` |
| Copy | `Ctrl+C` |
| Paste | `Ctrl+V` |
| Search Nodes | `Ctrl+Shift+F` |

---

## Troubleshooting

### "Graph needs an output node"

**Problem:** You tried to save without an Output node.

**Solution:**
1. Click the "Output" button in the node palette
2. Configure the output mapping
3. Save again

---

### "Cannot save empty graph"

**Problem:** The graph has no executable nodes.

**Solution:**
1. Add at least one node (Prompt, HTTP, Transform, etc.)
2. Note nodes don't count as executable nodes

---

### "Disconnected node detected"

**Problem:** A node isn't connected to the main workflow.

**Solution:**
1. Find the highlighted node
2. Connect it to another node with an edge
3. Or delete it if not needed

---

### Wizard won't open

**Problem:** The wizard button is disabled or not responding.

**Solution:**
1. Ensure you're in the graph editor (not viewing a run)
2. Check for JavaScript console errors
3. Refresh the page and try again

---

### Graph won't run after saving

**Problem:** The Run button is disabled.

**Solution:**
1. Check the validation status bar for errors
2. Ensure the graph has been saved (no asterisk in title)
3. Verify you have at least one complete path from start to output

---

## Next Steps

- Read the [Quick Reference Card](./wizard-quick-reference.md) for a one-page summary
- Explore the [Developer Documentation](../developer/wizard-architecture.md) to extend the wizard
- Check out example graphs in the graph library
