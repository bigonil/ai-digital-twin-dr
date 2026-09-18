# Ship Skill

Automated end-to-end commit and push workflow for shipping changes.

## Workflow

1. Stage all changes with `git add -A`
2. Generate a conventional commit message based on the diff
3. Commit and push to the current branch
4. If CHANGELOG.md exists, prepend an entry for this commit

## Usage

```
/ship
```

This skill is useful after implementing features, fixing bugs, or updating documentation when you want to commit all changes and push them to the remote branch in one operation.

## Commit Message Format

Uses conventional commits:
- `feat: ` — new feature
- `fix: ` — bug fix
- `docs: ` — documentation
- `refactor: ` — code refactor
- `test: ` — tests
- `chore: ` — build, dependencies, etc.

## CHANGELOG Updates

If `CHANGELOG.md` exists, the skill will prepend a new entry with:
- Commit date
- Commit message
- Related files changed
