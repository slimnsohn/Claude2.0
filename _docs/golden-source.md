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
