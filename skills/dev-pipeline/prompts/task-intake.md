# Task Intake - Generic Source Adapter

This document describes how to read tasks from different sources.

## Source Detection

Parse the user's input to determine the task source:

```
input = user's argument (e.g., "PDB-12345", "AB#456", "owner/repo#789", "path/to/task.md", "free text")

if input matches /^[A-Z][A-Z0-9_]+-\d+$/:
    source = "jira"
elif input matches /^AB#\d+$/ or (input matches /^#\d+$/ and azure_devops config exists):
    source = "azure-devops"
elif input matches /^[\w-]+\/[\w-]+#\d+$/:
    source = "github"
elif input matches /\.(md|txt|json)$/i and file exists at input path:
    source = "file"
else:
    source = "manual" (use input directly as task description)
```

## Source-Specific Reading

### Jira

**Detection:** Input matches `[A-Z]+-\d+` (e.g., `PDB-12345`, `AC-456`)

**Reading steps:**
1. Use `jira_jira_get_issue` MCP tool:
   ```
   jira_jira_get_issue(
     issue_key: "{INPUT}",
     fields: "description,reporter,assignee,priority,status,updated,labels,issuetype,summary,created,comment"
   )
   ```
2. Read comments (if not included in first call):
   ```
   jira_jira_get_issue(
     issue_key: "{INPUT}",
     fields: "comment",
     comment_limit: 20
   )
   ```
3. Extract: title, description (parse ADF if needed), type, priority, labels, comments, reporter, assignee

### Azure DevOps

**Detection:** Input matches `AB#\d+` or `#\d+` (with azure_devops config in AGENTS.md)

**Required config in AGENTS.md:**
```
azure_devops_org: myorg
azure_devops_project: MyProject
```

**Reading steps:**
1. Extract work item ID from input (remove `AB#` prefix)
2. Use bash tool:
   ```bash
   az boards work-item show --id {ID} --org https://dev.azure.com/{org} --project "{project}" --output json
   ```
3. If `az` CLI not available or not authenticated:
   ```bash
   # Try REST API
   $token = ":{PERSONAL_ACCESS_TOKEN}" | [Convert]::ToBase64String([System.Text.Encoding]::ASCII.GetBytes($_))
   Invoke-RestMethod -Uri "https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{ID}?api-version=7.0" -Headers @{Authorization="Basic $token"}
   ```
4. If authentication fails, ask user:
   ```
   Azure DevOps erişimi kurulamadı. Şunlardan birini yap:
   1. `az login` çalıştır ve tekrar dene
   2. AGENTS.md'ye azure_devops_pat: {token} ekle
   3. Task'ı manuel olarak açıklamana yaz, ben ondan devam edeyim
   ```
5. Extract: title, description, type, priority, assigned to, tags, comments

### GitHub Issues

**Detection:** Input matches `owner/repo#\d+`

**Reading steps:**
1. Extract owner, repo, issue number
2. Use bash tool:
   ```bash
   gh issue view {NUMBER} --repo {OWNER}/{REPO} --json title,body,labels,assignees,priority,state,comments
   ```
3. If `gh` not authenticated:
   ```bash
   gh auth login
   ```
4. Extract: title, body, labels, assignees, comments

### File

**Detection:** Input ends with `.md`, `.txt`, or `.json` and file exists

**Reading steps:**
1. Use `read` tool to read the file
2. Parse content based on file type:
   - `.md` / `.txt` → use content as-is
   - `.json` → parse and extract task fields

### Manual / Free Text

**Detection:** None of the above patterns match

**Reading steps:**
1. Use the input directly as the task description
2. Ask user for any missing details:
   ```
   Bu task için ek bilgi verir misin:
   - Tip: feature/bug/refactor/...
   - Öncelik: high/medium/low
   - Ek bağlam var mı?
   ```

## Post-Reading: Context Discovery

After reading the task from any source, discover project context:

```
1. Look for AGENTS.md in project root → read it
2. Look for CLAUDE.md in project root → read it
3. Look for .context/ directory → read relevant files
4. Look for README.md → read it
5. Use augmentcode_codebase-retrieval to understand current codebase state
6. If nothing found → ask user: "Proje context'i nerede?"
```

## Output

After completing TASK_INTAKE, you should have:
- **Task data:** title, description, type, priority, acceptance criteria (if available), comments
- **Project context:** architecture, conventions, relevant code
- **Current state:** what exists in the codebase related to this task

Present the summary to the user and WAIT for approval.
