# Repository Instructions

This file provides persistent instructions for AI agents and coding assistants working in the ThinApps Public Assets repository.

## Required Reading

Before reviewing or modifying this repository:

1. Read `readme.md` for the repository purpose and documentation index.
2. Read every document directly related to the requested change.
3. Read `docs/unsplash-compliance.md` before changing any Unsplash request, photo URL, attribution, tracking, caching, selection, or scheduling behavior.
4. Read `docs/github-actions.md` before changing workflow behavior, generated-data commits, concurrency, scheduling, secrets, limits, or timeouts.
5. Read `docs/photo-selection.md` before changing candidate ordering, cursor behavior, search queries, selection logic, attempt limits, or failure handling.
6. Read `docs/photo-data.md` and `docs/sync-and-cleanup.md` before changing the public schema, paths, placeholders, manifest, versioning, migration, pruning, or cleanup behavior.

Do not update one part of the pipeline in isolation when the change would make code, generated data, workflow behavior, or documentation contradict another active part of the repository.

## Instruction Precedence

Apply instructions in this order:

1. the user's current request and explicit approvals
2. the mandatory repository policy in this file, unless the user explicitly overrides a rule
3. the documented repository behavior and Unsplash integration guidance
4. existing repository conventions not covered above

Downstream consumers may use this data, but this repository remains the source of truth for its own public photo-data format and generation behavior.

## Repository Purpose

Preserve this repository as a focused public photo-metadata and synchronization pipeline for place imagery.

- Keep public photo records lightweight and deterministic.
- Preserve the `place_photos/` tree, `manifest.json`, `photos.json`, `version.json`, and `photo_cursor.json` roles described in the documentation.
- Treat generated files as pipeline outputs, not as arbitrary hand-maintained content.
- Do not turn this repository into a general asset dump, image mirror, stock-photo browser, crawler, or unrelated data store.
- Prefer small, focused changes that preserve compatibility with current consumers.

## Data Guardrails

- Do not store Unsplash image binaries in this repository.
- Do not replace Unsplash CDN image URLs with locally hosted or mirrored copies.
- Preserve required photo metadata, attribution fields, and valid place IDs.
- Treat records missing any required usable-photo field as incomplete, even when `image_url` is already populated; normal generation should repair those records by selecting a complete API-derived assignment rather than reconstructing attribution from the existing image URL.
- Do not manually bulk-edit generated photo records without understanding the synchronization, migration, manifest, version, and cursor rules.
- Do not bypass stale-file pruning safeguards or deletion thresholds merely to make a run succeed.
- Do not reset or rewrite `photo_cursor.json` casually; it is persistent operational state for the repair-and-fill portion of runs.
- Do not bump `version.json` for cursor-only progress when public photo availability has not changed.
- Preserve existing path and place-ID conventions unless a coordinated migration is explicitly approved.

## Unsplash Requirements

Preserve the Unsplash integration rules documented in `docs/unsplash-compliance.md`.

- Use API-provided Unsplash image URLs directly for rendering.
- Preserve visible photographer and Unsplash attribution in downstream consumers.
- Preserve the configured referral parameters on attribution URLs.
- Keep `UNSPLASH_ACCESS_KEY` secret and server-side; never commit it, print it, place it in generated JSON, or expose it to downstream HTML or JavaScript.
- When a newly selected or different photo assignment is actually persisted, including repair of an incomplete record, trigger the API-provided `links.download_location` tracking endpoint as documented.
- Do not trigger download tracking for dry runs, same-photo refreshes of already-complete records, or ordinary downstream page views.
- Do not repurpose the Unsplash integration for bulk catalog harvesting, resale, AI training, advertising inventory, or unrelated image collection.
- Before materially changing Unsplash behavior, verify the current official Unsplash API guidance rather than relying only on historical repository behavior.

The current scheduled workflow is intentionally bounded and product-specific. Preserve the narrow place-enrichment use case, bounded limits, attribution, tracking, and rate-limit behavior.

## Workflow Guardrails

This repository intentionally contains `.github/workflows/update-place-photos.yml`.

The workflow currently runs every three hours at 17 minutes past the hour and also supports `workflow_dispatch`; normal commits do not directly trigger it.

- Do not add `push`, `pull_request`, change or remove the scheduled cron, or add other triggers without explicit approval.
- Do not use GitHub Actions as a helper mechanism for normal repository edits.
- Do not casually increase the default attempt limit, API request volume, or timeout.
- Preserve concurrency protection and bounded runs unless a deliberate redesign is approved.
- Preserve real failures for invalid configuration, malformed data, unexpected API behavior, unsafe pruning, and Git conflicts.
- Do not broadly ignore command failures or suppress errors just to keep the workflow green.
- Treat workflow-generated commits as expected pipeline output; do not rewrite their history.
- Before changing scripts used by the workflow, consider both the current scheduled and manual execution paths and the documented scheduling constraints.

Because workflow runs can create commits independently of manual repository edits, fetch the latest target file immediately before every write and avoid overwriting changes made by another agent, user, or workflow run.

## Mandatory Repository Policy

- Work directly on the default `master` branch.
- Fetch the latest target file immediately before every write.
- Use exactly one changed file per commit for manual repository edits.
- Keep all approved related edits to one file together in that file's single commit.
- Commit separate documentation, scripts, workflow files, and generated-data files separately.
- Do not create temporary branches or pull requests.
- Do not use Git trees, Git blobs, helper patch workflows, squash, amend, force-push, or history rewriting.
- Do not create or modify workflow triggers unless explicitly requested.
- Avoid unrelated formatting, cleanup, renaming, or refactoring.
- After each repository change, report the commit SHA, commit message, and exact file changed.

The one-file-per-commit rule applies to manual repository edits. The existing photo-update workflow may commit multiple generated output files together when they represent one coherent pipeline result; do not split or rewrite those workflow-generated commits merely to satisfy the manual-edit rule.

If a requested change requires multiple files, make separate direct commits while preserving a valid intermediate repository state. If one-file commits would temporarily create a broken or unsafe state, stop and explain the dependency rather than violating the one-file rule.

## Change Review

Before completing a task:

- review the complete affected file, not only the edited lines
- check related documentation for stale or contradictory wording
- verify generated-data assumptions against the scripts that produce the data
- verify Unsplash-sensitive changes against `docs/unsplash-compliance.md`
- verify workflow-sensitive changes against the current workflow file and `docs/github-actions.md`
- preserve downstream compatibility unless a coordinated breaking change was explicitly approved
- avoid unnecessary churn in large generated JSON files
- state any unverified external requirement, limitation, or intentionally deferred follow-up clearly
