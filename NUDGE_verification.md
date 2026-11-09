Paste this into your **verification** session.

---

Catch up on coordination state before your next task. Your checkpoint is
behind — pull the full unread range and process it **in order**, not just the
first matching line, since one entry corrects a path given in an earlier one:

```
ssh <user>@login.htcf.wustl.edu 'tail -n +9 /lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/CHANGELOG.jsonl'
```

(You're at checkpoint 8 — this pulls everything from line 9 onward.)

Two things in there you need to act on:

1. **A new task assigned to you**: cross-check per-sample metadata *values*
   (donor, genotype, disease_status, tissue/cell type, sex, age) against each
   paper's own supplementary tables — not just counts against GEO, which is
   all your current metadata QC does. Full brief:
   `ssh <user>@login.htcf.wustl.edu 'cat /lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md'`
   Note: an earlier changelog line says this file is "at the EXTERNAL_DATASETS
   collection root" — that's now stale; it's at the coordination root, per the
   file-move event described next.

2. **File reorganization**: `PIPELINE_INSTRUCTIONS.md`, `conversion_process.md`,
   `METADATA_QC_FLAGS.md` (your own file), `PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md`,
   and `AMBIENT_RNA_RAW_DATA_AUDIT.md`/`.tsv` all moved out of the dataset
   collection root into the coordination root
   (`/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/`). Re-read
   `PROTOCOL.md` there for the updated ownership table and root descriptions —
   your own `METADATA_QC_FLAGS.md` is now at the coordination root, not
   `EXTERNAL_DATASETS`.

After you start work: per `PROTOCOL.md`, advance your checkpoint, update
`verification_status.json`'s `updated_at`, and append a changelog line noting
you've picked up the new task.
