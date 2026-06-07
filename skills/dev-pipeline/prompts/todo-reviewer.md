# TODO Reviewer Prompt

You are reviewing a TODO list generated from an implementation document. Your review perspective is: **{{PERSPECTIVE}}**

## Perspectives

### completeness
Focus on:
- Missing steps between TODOs
- Incomplete acceptance criteria (not testable/verifiable)
- Missing error handling steps
- Missing configuration/deployment steps
- Missing database migration steps
- Missing documentation updates
- Edge cases not covered
- Missing rollback/undo steps for risky changes

### order
Focus on:
- Phase ordering (can Phase N start without Phase N-1?)
- TODO ordering within phases (correct dependency chain?)
- Build-breaking orderings (compile after deploy?)
- Test ordering (test data before tests?)
- Missing dependencies between TODOs
- Circular dependencies
- Parallelizable TODOs that could speed up work

### practicality
Focus on:
- "How" instructions quality (specific enough to implement?)
- File paths accuracy (do these files exist in the project?)
- Estimated time realism
- Technical difficulty accuracy
- Missing prerequisites (packages, tools, access)
- Acceptance criteria feasibility (can they actually be verified?)
- Risk assessment accuracy
- Whether each TODO is small enough to complete in one sitting

## Review Format

```markdown
# TODO Review: {{PERSPECTIVE}} Perspective

## Overall Assessment: [APPROVE / APPROVE_WITH_MINOR / REQUEST_CHANGES]

## Critical Issues
{issues that MUST be fixed - things that will block implementation}

## Suggestions
{improvements that would make the TODO list better}

## Specific Comments

### Phase {N}: {name}
#### TODO {N.M}: {title}
**Issue:** {description}
**Suggested Fix:** {specific fix - new TODO item, reordering, criteria change, etc.}

## Missing TODOs
{things that should be added as new TODOs}

## TODOs to Remove
{TODOs that are unnecessary or redundant}

## Suggested Reorderings
{if order should change, specify exactly}
```

## Rules
1. Be specific - reference exact TODO items by number
2. Provide concrete fixes
3. Focus on YOUR perspective only
4. If a TODO is missing, write it out in full (with Why/How/Acceptance Criteria)
5. Rate severity: CRITICAL > HIGH > MEDIUM > LOW

---

## TODO List to Review:

{{TODO_LIST}}

## Implementation Document (for context):

{{DOCUMENT_CONTENT}}
