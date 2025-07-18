---
title: Architecture Decision Records
description: Architectural decisions and design rationale for the Meraki Dashboard Exporter
tags:
  - architecture
  - design
  - adr
---

# Architecture Decision Records (ADRs)

This section contains Architecture Decision Records (ADRs) that document important architectural decisions made during the development of the Meraki Dashboard Exporter. These records provide context, alternatives considered, and consequences of key design choices.

## What are ADRs?

Architecture Decision Records are short text documents that capture an important architectural decision along with its context and consequences. They help:

- **Preserve Knowledge**: Document why decisions were made
- **Reduce Debates**: Avoid re-arguing settled decisions
- **Speed Up New Team Members**: Understand the system's evolution
- **Enable Better Decisions**: Learn from past choices

## Format

Each ADR follows a consistent structure:

- **Status**: Accepted, Deprecated, Superseded
- **Context**: The situation requiring a decision
- **Decision**: What was decided
- **Consequences**: Positive and negative outcomes
- **Alternatives**: Options that were considered

## Current ADRs

<div class="grid cards" markdown>

- :material-sitemap: **[ADR-001: Collector Architecture](001-collector-architecture.md)**

    ---

    Hierarchical collector system with three-tier updates and metric ownership patterns

- :material-alert-octagon: **[ADR-002: Error Handling Strategy](002-error-handling-strategy.md)**

    ---

    Decorator-based error handling with categorization and graceful degradation

</div>

## Contributing

When making significant architectural decisions:

1. **Document the Decision**: Create a new ADR following the template
2. **Include Context**: Explain the problem and constraints
3. **List Alternatives**: Show what else was considered
4. **Describe Consequences**: Both positive and negative impacts

!!! tip "ADR Guidelines"
    - Keep ADRs focused on architecture, not implementation details
    - Write for future developers who weren't part of the decision
    - Update status when decisions are superseded or deprecated
    - Reference relevant ADRs when making related decisions
