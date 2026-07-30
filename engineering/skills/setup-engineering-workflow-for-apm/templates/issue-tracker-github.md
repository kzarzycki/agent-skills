# Issue tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues. Run `gh` commands
inside the repository so the CLI infers the remote.

## Operations

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state open --json number,title,body,labels`
- Comment: `gh issue comment <number> --body "..."`
- Label: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

When an engineering skill says to publish a ticket, create one GitHub issue per
ticket in dependency order. Use GitHub's native sub-issue and dependency
relationships when the repository enables them; otherwise record `Part of
#<map>` and `Blocked by: #<number>` in the issue body.

Pull requests are not a triage request surface unless this file says otherwise.
