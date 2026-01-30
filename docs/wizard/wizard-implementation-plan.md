# Agent Creation Wizard - Master Implementation Plan

## Executive Summary

This document outlines the complete refactor of ForgeGraph's graph editor to implement an interactive "Agent Creation Wizard" that guides users through building AI agent workflows with enforced best practices.

## Goals

1. **Guided Experience**: Step-by-step wizard for creating agent graphs
2. **Graph Validity**: Enforce Start/End node requirements with visual feedback
3. **Data Type Safety**: Track and validate data types between nodes
4. **Quick Templates**: Pre-built node presets for common patterns
5. **Always Runnable**: Valid graphs can be executed at any time during editing

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      GraphEditor (Enhanced)                     │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐│
│  │ AgentWizard  │  │ NodePalette  │  │    NodeInspector       ││
│  │ (Overlay)    │  │ + QuickNodes │  │    + NodeConfigDialog  ││
│  └──────────────┘  └──────────────┘  └────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              React Flow Canvas                              ││
│  │  + ValidationOverlay (Start/End indicators)                 ││
│  │  + DataTypeIndicators (Edge type badges)                    ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (Django)                             │
│  + Enhanced GraphValidator (Start/End/Type validation)          │
│  + Node schema definitions                                      │
│  + Quick template storage                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Engine (Go)                                  │
│  + Data type metadata propagation                               │
│  + Enhanced validation at execution                             │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Stages

### Stage 1: Foundation & UI Infrastructure
Build the base components and infrastructure for the wizard system.

**Deliverables:**
- Wizard context and state management
- Base dialog/overlay components
- Wizard entry point in GraphEditor

### Stage 2: Node Generator Forms
Create the universal node configuration dialog with per-type forms.

**Deliverables:**
- NodeConfigDialog component (Shadcn Dialog)
- Form layouts for all 10 node types
- Role, Job Description, Examples, Notes fields
- Form validation

### Stage 3: Graph Validation & Visual Feedback
Implement real-time validation with clear visual indicators.

**Deliverables:**
- Enhanced validation logic (frontend + backend)
- ValidationOverlay component
- Missing Start/End node indicators
- Error badge system

### Stage 4: Data Flow & Type Propagation
Track and display data types flowing between nodes.

**Deliverables:**
- Node output type definitions
- Edge type compatibility checking
- DataTypeIndicator component
- Type mismatch warnings

### Stage 5: Wizard Flow & Guided Experience
Build the step-by-step wizard experience.

**Deliverables:**
- AgentWizard orchestrator component
- Individual step components
- Progress indicator
- Contextual help/tooltips
- Quick Node presets (templates)

### Stage 6: Backend & Engine Updates
Update backend validation and engine for new features.

**Deliverables:**
- Enhanced GraphValidator rules
- Node schema storage
- Quick template API
- Engine type metadata support

### Stage 7: Testing & Documentation
Comprehensive testing and user documentation.

**Deliverables:**
- Jest unit tests for all new components
- Playwright E2E tests for wizard flow
- Updated user documentation

## Key Design Decisions

### 1. Wizard as Overlay (Not Separate Route)
The wizard will be an overlay on the existing canvas, not a separate page. This allows users to see their graph being built in real-time and maintains the "always runnable" requirement.

### 2. Node Configuration via Modal Dialog
Following the existing PromptNodeWizardDialog pattern, all node configuration will happen in a Shadcn Dialog modal. This provides focus and prevents accidental clicks.

### 3. START/END as Trigger/Output Nodes
Rather than literal "Start" and "End" node types, we use:
- **Start**: Edges from "START" sentinel (trigger edges)
- **End**: Nodes with `type: output` (or sink nodes marked as ends)

This aligns with the existing codebase architecture.

### 4. Data Types Stored in Node Config
Each node's output data type will be stored in its config:
```typescript
config: {
  // ... existing fields
  outputType: "text" | "json" | "image" | "file" | "any"
  outputSchema?: JSONSchema  // Optional detailed schema
}
```

### 5. Quick Nodes as Hardcoded Presets (Initially)
Quick Node templates will start as hardcoded presets in the frontend. Future iterations can add a management UI and backend storage.

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking existing graphs | Maintain backward compatibility; new fields optional |
| Performance with validation | Debounce validation; only validate on meaningful changes |
| Complex wizard state | Use React Context with clear state machine |
| Engine compatibility | Data types are metadata-only; execution unchanged |

## Success Criteria

1. Users can create a complete agent graph using only the wizard
2. Missing Start/End nodes show clear visual errors
3. Data types display on edges and warn on mismatches
4. Quick Node presets reduce setup time by 50%+
5. All existing graphs continue to work unchanged
6. Full test coverage for new functionality

## Timeline Estimate

| Stage | Estimated Effort |
|-------|-----------------|
| Stage 1 | Foundation |
| Stage 2 | Node Forms |
| Stage 3 | Validation |
| Stage 4 | Data Flow |
| Stage 5 | Wizard UX |
| Stage 6 | Backend |
| Stage 7 | Testing |

## Dependencies

- Shadcn Dialog component (already installed)
- React Flow custom nodes/edges (already used)
- Backend GraphValidator (exists, needs enhancement)
- Engine graph.go (exists, needs metadata fields)
