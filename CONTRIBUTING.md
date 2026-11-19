# Contributing

## How to work in this repo

This repo is structured for agent-driven development. Each layer (`language/`, `library/`, `protocol/`) has a `SPEC.md` that is a build instruction, not a design discussion. The intended loop:

1. Pick a spec (start with `language/` — it has no dependencies).
2. Implement the **First Milestone** section exactly as described.
3. Run the tests locally.
4. Open a PR with: the implementation, tests, CI config if missing, and a description covering (a) what you built, (b) what you deliberately deferred and why, (c) any deviations from the spec.

## Rules

- **Do not build the Deferred section.** Those items exist to prevent scope creep. If you believe something deferred should be built now, open an issue and argue it — don't just build it.
- **Justify language and framework choices in the PR.** The specs leave some choices open; the PR is where that decision gets recorded.
- **One milestone per PR.** If a spec's milestone is too large for one PR, split it and note the split in both PRs.
- **Tests are not optional.** A PR without tests for the acceptance criteria will be closed, not reviewed.
- **Spec changes go through issues first.** If the spec itself is wrong, file an issue before editing `SPEC.md` in a PR.

## CI

GitHub Actions should run on every PR: lint, test, and (for protocol) the integration test. The first PR for each layer is responsible for adding CI config if it is not already present.

## Philosophy

This repo optimizes for **reliable composition** across layers, not for any single layer being impressive in isolation. A beautiful renderer that cannot consume a valid document is a failure. A perfect schema with no runtime is a file format. The value is in the seams.