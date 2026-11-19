---
name: Pull Request
about: Submit an implementation for review
title: ''
labels: ''
assignees: ''

---

**Layer:** (language / library / protocol)

**Spec milestone:** (paste or link the First Milestone section you implemented)

## Summary

What you built, in 2-4 sentences.

## What I deliberately deferred

List anything from the spec's Deferred section or anything you chose not to build, with a one-line reason each.

## Deviations from the spec

Any place where the implementation differs from SPEC.md. If none, say "None." If there are deviations, explain why each was necessary.

## Test plan

- [ ] All acceptance criteria from the spec are met
- [ ] Tests cover every acceptance criterion
- [ ] CI passes
- [ ] (Protocol layer) Integration test runs server + client end-to-end

## Checklist

- [ ] One milestone per PR
- [ ] Language/framework choice justified in the PR body
- [ ] No Deferred-section items were built
- [ ] Spec changes (if any) went through an issue first