Paste this into your **conversion** session.

---

Catch up on coordination state before continuing your current queue. Your
checkpoint is badly behind — 266, while the shared changelog is now at 451
lines (~185 events unseen). Pull the full unread range and process it **in
order**, not just the first matching line:

```
ssh <user>@login.htcf.wustl.edu 'tail -n +267 /lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/CHANGELOG.jsonl'
```

Three things in there you need to act on:

1. **A new task assigned to you (2026-09-28)**: backfill the canonical
   vocabulary columns (`disease_status_canonical`, `tissue`, `cell_type`,
   `genotype_canonical`) into the already-converted `.h5ad` files for 12 of
   the 14 Tier-1 single-cell studies — `downstream_verification` found 0/22
   files carry these columns in `adata.obs` even though `samples.json` has
   them. This is a metadata-only patch (join by `sample_id`, write new obs
   columns, write file back out) — it is NOT a re-conversion and NOT a
   DecontX re-run. Full study list, mechanics, and required
   before/after-untouched verification are in that task_assigned entry.

2. **A permanent policy addition to `PIPELINE_INSTRUCTIONS.md` Section 4a**
   (also 2026-09-28, same day): `Brain2025_Multiome` and
   `CrypticExon_ActaNeuropathol2023` are permanently excluded from this
   backfill (and from any future one) — do not touch `cell_type` in either
   study's `.h5ad` under any circumstance. Read the new "PERMANENT EXCEPTION"
   paragraph in Section 4a directly before starting item 1 — it explains why
   (no `normalized` block exists for these 2 studies' records at all; each
   record is a whole multi-donor file with many real cell types, not one
   sample; both already have a real per-cell `cell_type` column that is also
   what their own DecontX runs used as cluster-label input, and a same-named
   write would silently destroy it).

3. **Your own `conversion_tasks.json` current_task description is stale** —
   it still lists GSE122649_dataset/GSE252892_dataset/GSE326354_dataset as
   "remaining" even though all 3 are already converted (confirmed on disk).
   Update it to reflect real current state (in-progress GSE310723_dataset,
   remaining GSE315972_dataset/Itou2024_scRNA_Zenodo/Dhawka2025_CyTOF, plus
   the new backfill task from item 1) so the next status check — yours or
   the orchestrator's — isn't reading old information.

After processing, advance your checkpoint file to the new line count so this
doesn't happen again next time.
