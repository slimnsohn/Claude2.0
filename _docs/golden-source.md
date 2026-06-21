# Golden Source: `main`

**`main` is the single source of truth for this workspace.** Every project lives on
`main`. If you can't find an app on `main`, that is a bug to fix — not the normal state.

## Where apps live (on `main`)

| Folder         | Holds                                         |
|----------------|-----------------------------------------------|
| `apps/<name>`  | Active projects under development             |
| `shipped/<name>` | Deployed / stable projects                   |
| `sandbox/`     | Throwaway experiments (NOT promised on `main`) |

A finished app should be visible on `main` in `apps/` or `shipped/`. The `shipped/`
folder is where deployed projects go — `start.bat` (browser apps) and
`start.bat` + `launch.vbs` (Electron apps) must be present there.

## Branch flow

- Develop each app on its own `app/<name>` branch (see memory `feedback_app_branches`).
- **When work on a branch is finished, consolidate it back to `main`.** Don't let
  `main` fall behind — a branch that never merges is how apps "disappear."
- "Shipping" an app = promote it to `shipped/<name>` **and** make sure that promotion
  lands on `main`, not only on the feature branch.

## Maintaining shipped apps (post-ship)

`shipped/` is **maintenance mode, not a graveyard.** An app stays in `shipped/<name>`
for its whole life and keeps getting bug fixes and features from there. The invariant:

> **Anything in `shipped/` on `main` is always deployment-ready.**

So you never edit a shipped app in place on `main`. You branch, fix, test, merge —
the same loop used for new apps, just pointed at an existing `shipped/` folder.

### The change loop (bug fix or new feature on a shipped app)

1. `git checkout main && git pull` — start from golden source
2. `git checkout -b app/<name>` — fix/feature branch
3. make the change + write/update tests
4. tests pass → run the `security-audit` skill
5. merge `app/<name>` back into `main`
6. tag a checkpoint + redeploy (see below)

A major rewrite — where the live version must stay untouched while you rebuild — is the
only reason to move an app back to `apps/`; re-promote to `shipped/` when stable again.

### Checkpoints (so you can revert a bad deploy)

Every deploy gets an annotated git tag. That tag **is** the rollback point.

- Tag format: `<app>-vMAJOR.MINOR` — e.g. `nautilus-v1.0`, then `nautilus-v1.1`
- Create: `git tag -a nautilus-v1.1 -m "what changed"` then `git push --tags`
- List history: `git tag -l 'nautilus-*'`
- Revert: restore just that app from the last good tag —
  `git checkout nautilus-v1.0 -- shipped/nautilus`, or branch a hotfix from it —
  `git checkout -b hotfix/nautilus nautilus-v1.0`

Bump **MINOR** for features/fixes, **MAJOR** for breaking reworks. Tag *after* the merge
to `main`, so every tag is a real, deployable point on the golden source.

## The failure this prevents

On 2026-06-12 every app was stranded on its own `app/*` / `feat/*` branch and `main`
had almost nothing. The shipped Nautilus app (incl. its `start.bat`) existed only on
`app/nautilus`, so it was invisible from the working branch. All apps were then
consolidated onto `main`. To keep it from recurring: **after finishing any branch,
merge/fast-forward `main` so `main` always reflects reality.**

## Exceptions

A project may live outside this workspace's `main` only if it *explicitly* needs to
(e.g. its own deployment repo, a separate Git remote, size/licensing constraints).
When that happens, record the exception here with a one-line reason and a pointer to
where it actually lives.

_(No active exceptions today.)_
