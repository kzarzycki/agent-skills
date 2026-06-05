Implement this task and NOTHING else:

{{TASK_DESC}}

Restrict ALL edits to these files ONLY: {{FILE_SCOPE}}. Other tasks own the other
files and run before/after you on the same working tree; do not touch anything
outside this scope, and do not edit other files to make the build green.

Honor these project rules (gathered for the files you are touching):
{{RULES_BUNDLE}}

Follow TDD where it applies: write the failing test first, then the minimal code
to pass it. Read what you need for context, then make the edits with
Edit/MultiEdit/Write.

You MAY run `{{VERIFY_CMD}}` to sanity-check your own files, but the FULL suite may
not pass yet: sibling tasks that edit other files land separately, and an
integrated verify runs after all tasks complete. Do NOT try to fix errors that
originate outside your file scope (e.g. an import another task will remove). Do
NOT commit.

Return the list of files you changed and a one-paragraph summary.
