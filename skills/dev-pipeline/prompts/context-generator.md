# Context Generator - Codebase Analysis

This document describes how to generate project context from a codebase when no pre-existing context directory is available.

## Goal

Analyze the codebase and create a structured context directory that DQG and the pipeline can use to understand the project's architecture, conventions, domain, and patterns.

## Analysis Steps

### Step 1: Read Existing Documentation

Use `read` tool to check for these files in the project root:
1. `AGENTS.md` → project instructions, commands, architecture notes
2. `CLAUDE.md` → same as above (different AI tool convention)
3. `GEMINI.md` → same as above
4. `README.md` → project overview, setup instructions
5. `.context/` directory → if it exists but is incomplete, use what's there

### Step 2: Codebase Queries

Use `augmentcode_codebase-retrieval` with these queries (run multiple in parallel):

1. **Architecture query:**
   ```
   "What is the project architecture? What are the main modules, layers, and how do they interact? 
    What is the entry point? What frameworks are used?"
   ```

2. **Conventions query:**
   ```
   "What coding conventions and patterns are used in this project? 
    Naming conventions, file organization, error handling patterns, logging patterns."
   ```

3. **Domain query:**
   ```
   "What is the domain model? What are the core business entities and their relationships? 
    What are the main business rules and workflows?"
   ```

4. **Patterns query:**
   ```
   "What design patterns and architectural patterns are used? 
    Dependency injection, repository pattern, service layer, middleware, etc."
   ```

5. **Infrastructure query:**
   ```
   "What infrastructure is used? Database type, caching, message queues, 
    external API integrations, authentication/authorization approach."
   ```

6. **Tech stack query:**
   ```
   "What is the technology stack? Language, framework version, build tools, 
    test framework, package manager, key libraries."
   ```

### Step 3: Investigate Key Files

Use `glob` and `grep` to find and read key structural files:

- Package/dependency files: `package.json`, `requirements.txt`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, `*.csproj`, `*.sln`
- Config files: `tsconfig.json`, `webpack.config.*`, `vite.config.*`, `docker-compose.yml`, `Dockerfile`
- Database schemas: `migrations/`, `*.sql`, `prisma/schema.prisma`, `models/`
- API definitions: `routes/`, `controllers/`, `api/`, `openapi.*`, `swagger.*`
- Test files: `tests/`, `__tests__/`, `*.test.*`, `*.spec.*`

### Step 4: Generate Context Files

Synthesize all gathered information into 4 context files.

#### architecture.md

```markdown
# Project Architecture

## Overview
{1-2 paragraph description of what the project does and its high-level architecture}

## Technology Stack
- **Language:** {language} {version}
- **Framework:** {framework} {version}
- **Build Tool:** {tool}
- **Test Framework:** {framework}
- **Package Manager:** {manager}

## Module Structure
{Describe the main directories and their purposes}

## Layer Architecture
{Describe layers if applicable: presentation, business, data, infrastructure}

## Entry Points
{HTTP endpoints, CLI commands, job triggers, etc.}

## Data Flow
{How data flows through the system}

## External Integrations
{Third-party APIs, databases, message queues, etc.}
```

#### conventions.md

```markdown
# Coding Conventions

## File Organization
{How files are organized, naming conventions}

## Naming Conventions
- **Files:** {convention}
- **Classes:** {convention}
- **Functions/Methods:** {convention}
- **Variables:** {convention}
- **Constants:** {convention}

## Error Handling
{How errors are handled, custom exception types, error response format}

## Logging
{Logging framework, log levels, log format}

## Testing Conventions
{Test file location, naming, mocking approach}

## Code Style
{Important style rules, linting config}
```

#### domain.md

```markdown
# Domain Model

## Core Entities
{List and describe the main business entities}

## Entity Relationships
{How entities relate to each other}

## Business Rules
{Key business rules and validations}

## Workflows
{Main business workflows / use cases}

## Glossary
{Domain-specific terms and their definitions}
```

#### patterns.md

```markdown
# Design Patterns

## Architecture Patterns
{Patterns used: MVC, Clean Architecture, CQRS, Event-Driven, etc.}

## Design Patterns
{Repository, Service, Factory, Strategy, etc.}

## Common Implementations
{How common tasks are typically done in this project:
 - Creating a new API endpoint
 - Adding a new database entity
 - Implementing a new feature
 - Adding a new test}

## Dependency Injection
{How DI is handled, IoC container}

## Data Access
{ORM, query patterns, repository pattern}
```

### Step 5: Save and Present

1. Create `.pipeline/context/` directory
2. Write all 4 files
3. Present summary to user (as defined in SKILL.md PHASE 1.5)
4. WAIT for user approval

## Important Notes

1. **Accuracy:** Only include information you found in the codebase. Do NOT guess or invent.
2. **Conciseness:** Each file should be 50-200 lines. Not too short (useless) not too long (noise).
3. **Structure:** Follow the templates above. Keep section headers consistent.
4. **Language:** Use English for technical terms, but project's primary language for descriptions.
5. **Uncertainty:** If you're not sure about something, note it as "[UNVERIFIED - needs confirmation]"
6. **Incremental:** Start with what you know from documentation, then enhance with codebase analysis.
