Implement this task and NOTHING else:

{{TASK_DESC}}

Restrict ALL edits to these files ONLY: {{FILE_SCOPE}}. Another implementer is
working elsewhere in the repo concurrently — do not touch any other file.

Honor these project rules (gathered for the files you are touching):
{{RULES_BUNDLE}}

Follow TDD: write the failing test first, then the minimal code to pass it.
Read what you need for context, make the edits with Edit/MultiEdit/Write, then
run `{{VERIFY_CMD}}` once; if it fails, fix it within the allowed files. Do NOT commit.
Return the list of files you changed and a one-paragraph summary.
