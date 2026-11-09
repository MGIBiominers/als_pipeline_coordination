Paste this into your **download_metadata** session.

---

Your checkpoint into the shared changelog is stuck at line 23, but the log is
now at 95 lines — you've missed roughly 70 events from `verification`,
`conversion`, and the orchestrating session while working on the FASTQ
barcode-read investigation. Pull everything you haven't seen yet:

```
ssh <user>@login.htcf.wustl.edu 'tail -n +24 /lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/CHANGELOG.jsonl'
```

Several of these are confirmed metadata corrections that are yours to apply
(`samples.json`/`studies.tsv`/`all_samples.tsv` are your files) — don't just
skim, actually go fix these:

1. **`Pineda2024_Cell`** — `source_doi_or_pmid` is wrong for all 66 GSMs.
   Currently `10.1016/j.cell.2024.02.031` (a different, later paper covering a
   different cohort/BioProject). Correct value:
   `10.1101/2021.07.07.451374` (the actual 2021 bioRxiv preprint whose cohort
   is GSE174332). Confirmed independently via GEO esummary + PMC full text of
   the wrongly-cited paper.
2. **`Tam2019_GSE124439`** — a 3-sample category-count mismatch between your
   `sample group` characteristic distribution and the paper's Figure legend
   (145/14/17 vs. paper's 148/11/17). Not yet resolved to specific GSMs —
   may need the paper's supplementary donor table.
3. **`OFC_APA_CellGenomics2025`** — a donor-count discrepancy (your metadata
   has 25 donors, paper's cohort sentence states 23) — read the flag closely,
   part of this is a legitimate scope difference (an asymptomatic carrier
   donor correctly excluded from the paper's headline count, not an error on
   your side) but the `C9ALSFTLD` 7-vs-6 split is still unresolved.
4. **`Ma2025_GSE299997`** and **`pTDP43_PNAS2025`** — completeness gaps
   (null `disease_status`/`genotype`/`timepoint_or_age`) where the fix is
   directly derivable from data you already have (see the flag text for the
   exact mapping rule) — no new external lookup needed.

Also note: a new role, `alignment`, was created since your last read — it
handles FASTQ→count-matrix alignment for `OFC_APA_CellGenomics2025` and
`Pineda2024_Cell` once their downloads are genuinely complete. Given what
you're finding about the barcode-read issue, `alignment` needs to know the
true state of these downloads — make sure your `download_status.json` note
reflects the real, corrected picture once your re-fetch fix is validated and
rolled out, not the pre-barcode-bug numbers.

**Read `PROTOCOL.md` in full again** — several things changed since your last
read: the `task_started`/`current_task` convention (which you already seem to
be following correctly — good), and the checkpoint mechanism itself is the
exact thing that just failed here. When you finish this catch-up, set your
checkpoint to the *current* total line count of `CHANGELOG.jsonl` — not the
count from when you started reading, since more may land while you work.
