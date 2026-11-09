# ALS Dataset Collection — Unified Format Conversion Pipeline

> **Multi-session coordination:** this collection is shared with a concurrent
> download/metadata session and a verification session. Before starting work,
> read `/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/PROTOCOL.md` and check `/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/CHANGELOG.jsonl`
> since your last checkpoint (`/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/checkpoints/conversion.txt`).
> Update `/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/conversion_status.json` (your own file) as you go —
> don't start converting a study without checking the other two sessions'
> status files for a lock, a `verify_failed`, or a not-yet-`downloaded` state.

**Target audience:** Claude Code, building a conversion pipeline on WashU HTCF.
**Collection root:** `/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS`
**Compute:** HTCF Slurm cluster (partitions: `general`, `interactive`, `gpu`, `squash`). `/lts` is
**read-only from compute nodes** — write all outputs to a scratch directory
(`/scratch/rmlab/rmlab_shared3/<user>/...`), verify, then copy back to `/lts` via a
login-node command. See "Execution constraints" below before writing any job scripts.

## 1. Goal

Convert the collection's raw, heterogeneous per-study downloads into a small number
of standardized formats, one file per study (never merge studies into a combined
object at this stage — that is a deliberate downstream analysis step, not part of
format standardization). Attach normalized sample metadata (already built — see
Section 4) to every converted object so cross-study filtering works without
re-deriving anything from raw characteristics text.

## 2. Format policy by data type

Do NOT force everything into one format. Route by assay type:

| Assay type | Target format | Library |
|---|---|---|
| scRNA-seq / snRNA-seq (droplet, 10x-style) | AnnData `.h5ad` | `scanpy` (`sc.read_10x_h5`, `sc.read_10x_mtx`, `sc.read_h5ad`, `sc.read_csv` as needed) |
| snRNA-seq + snATAC-seq (multiome, paired) | MuData `.h5mu` (RNA + ATAC modalities linked in one object) | `mudata`, `muon` |
| Bulk RNA-seq | Sample x gene matrix, **Parquet** (primary) + plain TSV (human-readable copy) — do NOT wrap in AnnData | `pandas` |
| Bulk ChIP-seq (H3K27ac) | Leave as bigWig + narrowPeak/broadPeak — no matrix conversion. Optionally, as a SEPARATE derived product (not part of this pipeline unless requested), a peak x sample count matrix via `deeptools multiBigwigSummary` | n/a for base conversion |
| CELLxGENE h5ad (already h5ad) | No conversion — copy as-is into `processed/`, just attach the normalized metadata columns if missing | `scanpy` |

For every converted `.h5ad`/`.h5mu`:
- Store the RAW/unfiltered counts (before any additional filtering you apply) in
  `adata.layers["raw"]`. Several sources are already filtered/corrected upstream by
  the original authors (e.g. DivergentC9's cellBender-corrected `.h5`, Lall's
  "filtered_genesummed" CSVs) — do not re-filter those; just note in
  `adata.uns["processing_notes"]` what filtering the ORIGINAL AUTHORS already did,
  sourced from each study's `README.md` / `series_metadata.json`.
- Attach per-sample metadata from `all_samples.tsv` / `samples.json`'s `normalized`
  block into `adata.obs` (see Section 4) — join on `sample_id` (GSM accession).
- Write a `processed/conversion_log.md` per study documenting: source file(s),
  target file, library+version used, filtering applied (or explicitly "none —
  used author-filtered matrix as-is"), row/column counts before and after, and the
  date.

### 2a. Final h5ad/h5mu layer and obs schema (comprehensive reference, added 2026-07-27)

This is the definitive list of what every converted object should carry. Keep
it up to date if you add another study-specific field — this section exists so
no one has to reverse-engineer the schema from example files.

**Always present** (every converted `.h5ad`'s RNA modality, or `.h5mu`'s `rna` modality):
- `X` — the primary/working expression matrix (author-provided filtered counts,
  or cellBender-corrected where the authors provided that as the primary file —
  see Section 3's per-study notes for which).
- `layers["raw"]` — pre-any-pipeline-filtering counts, per the bullet above.
  Note: this means "before OUR pipeline's own filtering," not necessarily "the
  true empty-droplet-inclusive barcode-space matrix" — for most studies those
  are the same file, since we don't have the latter at all (see
  `AMBIENT_RNA_RAW_DATA_AUDIT.md` at the coordination root).
  **HARD REQUIREMENT (tightened 2026-07-29, external collaborator's DESeq2
  tooling depends on this): `layers["raw"]` must be a genuine, always-present
  `.layers` entry holding whole-number counts, in EVERY droplet-based h5ad —
  never "just read X instead, it's equivalent here" as an implicit substitute.**
  A spot-check across all 8 droplet studies with DecontX in scope found this
  currently violated in 4 of them:
  - `Qki5_PNAS2024`, `DivergentC9_NatComms2023` — no `layers["raw"]` at all;
    `X` itself already holds the true raw integer counts (confirmed: Qki5's X
    and DivergentC9's X are both whole-number-valued) but was never also
    copied into `layers["raw"]`.
  - `Brain2025_Multiome`, `CrypticExon_ActaNeuropathol2023` — no
    `layers["raw"]` at all, AND `X` is **not** raw here (it's CELLxGENE's
    normalized/log-transformed expression, confirmed non-integer: sample
    values ~0.15–6.7). The true raw integer counts for these two live in
    AnnData's dedicated **`.raw.X`** slot instead (confirmed whole-number-
    valued, e.g. Brain2025_Multiome's `.raw.X` ranges 1–1326). This is a
    consequence of Section 2's "CELLxGENE h5ad — copy as-is, no conversion"
    policy never having been checked against this specific requirement before.
  **Fix required for all 4:** copy the true raw integer counts into a real
  `adata.layers["raw"]` (from `X` for the first two, from `.raw.X` for the
  latter two) so every study in the collection exposes the same layer name
  for "give me integer counts" — do not leave any of these relying on `X` or
  `.raw.X` as an implicit stand-in. Note in each study's `processing_notes`
  which slot `layers["raw"]` was actually sourced from. This is a targeted,
  additive fix (like DecontX itself) — does not require touching anything
  else already in these files.
- `obs[...]` — the normalized metadata schema fields per Section 4 (`study_id`,
  `accession`, `sample_id`, `assay_type`, `sample_source`, `organism`,
  `cell_line_or_donor`, `genotype`, `disease_status`, `tissue_or_cell_type`,
  `timepoint_or_age`, `treatment`, `sex`, `platform`, `batch`, `file_names`,
  `is_filtered`, `source_doi_or_pmid`, plus any `extra_*` fields that apply).
- `uns["processing_notes"]` — free text: what filtering the original authors
  already applied, and (once run — see 2b) what DecontX processing was applied.

**Added by DecontX ambient-RNA correction** (droplet-based scRNA-seq/snRNA-seq
studies only — see Section 2b for exact scope):
- `layers["decontx_corrected"]` — DecontX's `decontXcounts()` output: the
  ambient-RNA-corrected count matrix.
- `obs["decontx_contamination"]` — DecontX's `colData()$decontX_contamination`
  output: a per-cell estimated contamination proportion (0-1), kept for QC/
  reference even though it isn't a correction itself.

**Study-specific extras already established** (keep, don't remove):
- `layers["rpkm"]` — `Schweingruber2025_NatComms` only (alternate normalized layer).
- `layers["raw_precorrection"]` — `DivergentC9_NatComms2023` only, for GSM6781920
  specifically (the one GSM lacking a cellBender file — its raw triplet is used
  as both `X` and this layer, clearly flagged in `processing_notes`).
- `obs["barcode_pool"]`, `obs["barcode_disease_group"]` — `NatureAging2024_ETneurons`
  only (recovered from barcode structure, not from GEO metadata).

**Cross-compatibility note:** the external collaborator's own tooling
(`commons`'s `pick_counts()`, see `conversion_process.md`'s ambient-RNA section
for how this was found) looks for `layers['counts']` or AnnData's dedicated
`.raw` slot when auto-selecting a count matrix — NOT `layers['raw']`, which is
this pipeline's own established name and is a plain `.layers` entry, not the
`.raw` slot. This is a pre-existing naming mismatch, not something DecontX
introduces. Don't silently rename anything to fix it — flag it to the user if
it comes up; it's their call whether to rename or tell the collaborator to
look for `layers['raw']`/`layers['decontx_corrected']` explicitly.

### 2b. Ambient RNA correction — DecontX (added 2026-07-27)

**Why:** an external collaborator found a classic ambient-RNA contamination
pattern (pan-neuronal genes — STMN2, SNAP25, NEFL, NRGN, SYT1 — spuriously
elevated in glial cell types in ALS samples) in `Brain2025_Multiome` and
`CrypticExon_ActaNeuropathol2023`, consistent with a known caveat already
documented for `Pineda2024_Cell` elsewhere. CellBender/SoupX (the usual fix)
need the true unfiltered, empty-droplet-inclusive barcode matrix to estimate
ambient background — `AMBIENT_RNA_RAW_DATA_AUDIT.md` (coordination root)
confirms we only have that for one study (`DivergentC9_NatComms2023`,
snRNA arm). **DecontX** (part of Bioconductor's `celda` package) was chosen
instead specifically because it does NOT require raw/empty-droplet data — its
Bayesian model estimates each cell's contamination fraction using only the
already-downloaded *filtered* matrix, by comparing a cell's expression against
other cell-type clusters' consensus profiles in the same sample. Confirmed
directly against Bioconductor's own documentation before adopting this: the
`background` (raw-matrix) parameter to `decontX()` is optional, used only to
improve accuracy when some cells were lost pre-filtering — it is not a
requirement to run the tool at all.

**Scope — applies to** (per `AMBIENT_RNA_RAW_DATA_AUDIT.md`'s droplet-based
study list): `DivergentC9_NatComms2023` (snRNA arm only), `Zelic2025_Immunity`
(all 3 scRNA series), `HammellOneill2025_CellReports`, `Qki5_PNAS2024` (the
scRNA h5ad only, not its bulk tables), `Ho2021_CellSystems`,
`NatureAging2024_ETneurons`, `Lall2025_CellStemCell` (snRNA arm, if/when
unblocked), `pTDP43_PNAS2025` (RNA arm only, not ATAC), `Brain2025_Multiome`
(RNA side), `CrypticExon_ActaNeuropathol2023`.

**Does NOT apply to**: `Schweingruber2025_NatComms` (Smart-seq2 plate-based —
no droplet/empty-droplet pool concept applies), any bulk RNA-seq/ChIP-seq/
ATAC-only companion data within these same studies, or `OFC_APA_CellGenomics2025`
until a real count matrix exists at all (currently FASTQ-only, out of scope
per Section 6 until CellRanger produces one — once it does, build DecontX
into that conversion from the start, same as any other droplet study, not as
a separate follow-up pass). `Pineda2024_Cell` no longer belongs in this
exception list — it now has real `raw_feature_bc_matrix.h5` output for all
154 samples (Section 3), so it DOES apply here like any other droplet study.

**How to run it:**
- Package: `celda`'s `decontX()` (R/Bioconductor). This needs its own R
  environment — separate from the existing Python `als_pipeline_env` — set one
  up at `/ref/rmlab/software/azamat/als_pipeline_r_env` (or similar) with
  Bioconductor + `celda` installed. Your call on the exact setup approach
  (conda-forge R + BiocManager, or another route) — just document the version
  in `conversion_log.md` the same way the Python venv's packages are documented.
- Input: convert the assembled AnnData's count matrix to a `SingleCellExperiment`
  or plain sparse matrix for R (via `zellkonverter`, `anndata2ri`, or a manual
  barcodes/features/matrix export+reimport — implementation detail, your choice).
- Cluster labels: prefer real per-cell cell-type annotations where they already
  exist natively (`Brain2025_Multiome` and `CrypticExon_ActaNeuropathol2023`
  carry CELLxGENE ontology-mapped cell-type columns already); fall back to
  DecontX's own internal auto-clustering for every other study. Note which
  approach was used, per study, in `uns["processing_notes"]`.
  **This is a correction-quality requirement, not a style preference (external
  collaborator finding, 2026-08-03):** DecontX needs to know a cell is an
  astrocyte to correctly call a neuronal transcript found in it "contamination"
  — auto-clustering's unsupervised clusters don't carry that biological
  identity, so on real mixed-cell-type tissue, using native cell-type labels
  measurably changes (improves) the correction itself, not just how easy it is
  to validate afterward. Always check for a usable native cell-type column
  before falling back to auto-clustering, on every study, not just the two
  listed above.
  **Known validation-blocker, not a pipeline bug:** `Ho2021_CellSystems` is an
  iPSC-derived motor-neuron *culture*, not postmortem tissue — it has almost no
  glia at all (GFAP+ in ~0.2% of cells, confirmed by the collaborator) — so no
  amount of correct DecontX plumbing or cell-type labeling can demonstrate the
  neuronal-into-glial ambient-RNA pattern on this study; it is structurally the
  wrong dataset for that specific validation, independent of anything else.
  Separately (also found 2026-08-03, real gap): `Ho2021_CellSystems`'s
  `tissue_or_cell_type` and `disease_status` obs columns are both `"NA"`
  (`null` in the underlying `samples.json`) for every record — flagged to
  `download_metadata` (see changelog), since `genotype` (populated: "ALS
  C9orf72"/"ALS sporadic"/"Control"/"Isogenic Control") and `sample_source`
  (populated: "iPSC"/"iPSC-derived motor neurons") both already carry
  derivable values for these two null fields, same pattern as the earlier
  `Ma2025_GSE299997` fix.
- `background` parameter: pass the true raw/unfiltered triplet **only** for
  `DivergentC9_NatComms2023` (the one study where it exists — see
  `AMBIENT_RNA_RAW_DATA_AUDIT.md`). Omit it entirely for every other study —
  running DecontX on the filtered matrix alone, with no `background`, is the
  whole point of choosing this method over CellBender/SoupX.
- **`batch` parameter — REQUIRED whenever a study's converted object pools
  more than one capture together** (added 2026-07-29, external collaborator
  finding): every one of this collection's converted h5ads is one file per
  *study*, built by concatenating each GSM's own filtered matrix — but each
  GSM is ordinarily its own separate 10x capture/GEM well, with its own
  independent ambient-RNA pool. Calling `decontX()` on the concatenated
  object with no `batch` argument estimates a single ambient profile pooled
  across every capture in the file, which is wrong for all of them the same
  way running DecontX across unrelated samples would be. Confirmed as a real,
  not theoretical, gap: `Ho2021_CellSystems`'s already-`converted`+structurally-
  `verified` DecontX output has 21,298 cells spanning 25 distinct `sample_id`
  values run through one un-batched call.
  Default: pass `adata.obs["sample_id"]` (the GSM) as `batch=` — this is the
  correct capture-lane proxy for every study currently in scope, since none of
  them are known to multiplex more than one physical capture under a single
  GSM (hashing/demuxed pooled donors sharing one GEM well). If you find a study
  where that assumption doesn't hold — a GSM that itself represents multiple
  pooled captures — do not guess; `flag_for_owner` (orchestrator) with the
  specifics before proceeding, since the correct grouping in that case is
  something more granular than `sample_id`. For a study whose converted object
  already has only one distinct `sample_id` value (e.g. `NatureAging2024_ETneurons`),
  passing `batch` is a no-op — fine to include unconditionally rather than
  special-casing it away.
  **Known exception (found 2026-08-05, resolved 2026-08-10):**
  `CrypticExon_ActaNeuropathol2023`'s `sample_id` is a single CELLxGENE
  dataset-level UUID (one value for every cell in each of its 4 files) — not a
  per-capture identifier at all. Correctly flagged rather than guessed. Use
  `obs["sample"]` instead for this study specifically (26/22/21/15 distinct
  values across the 4 files, maps closely to `cell_line_or_donor` donor codes,
  splits into plausible per-capture-sized cell groups) — confirmed as the
  right proxy and approved. If any other CELLxGENE-sourced study is added
  later, check `sample_id`'s distinct-value count before trusting the default.
  Interaction with `background`: `DivergentC9_NatComms2023` is the one study
  using both `batch` and `background` together. `decontX()`'s `background`
  parameter is not itself a study-level scalar — Bioconductor's own
  documentation on `background` describes the case of *raw matrices captured
  in the same batch structure as `x`*, i.e. `batch` and `background` are meant
  to work together (the background matrix should carry a comparable batch
  vector so decontX can match each cell's own capture to its own empty-droplet
  pool, not one background pool applied globally against the batch-split
  counts). Confirm this against the installed `celda` 1.26.0 docs before
  wiring it up (`?decontX`, `background` and `batch` argument descriptions)
  rather than assuming this note's paraphrase is complete — your call how to
  structure the export if `background`'s own batch structure differs from
  `counts`'s.
- Output: write `decontXcounts(sce)` into `adata.layers["decontx_corrected"]`
  and `colData(sce)$decontX_contamination` into `adata.obs["decontx_contamination"]`
  (see Section 2a). Do **not** overwrite `X` or `layers["raw"]` — this is a
  purely additive step, so anything already consuming those two fields keeps
  working unchanged.
- Verification: after correcting, spot-check that the specific markers the
  collaborator flagged (STMN2, SNAP25, NEFL, NRGN, SYT1) are no longer
  spuriously elevated in glial clusters (astro/oligo/micro/OPC) within
  `layers["decontx_corrected"]`, for at least the studies where the pattern was
  originally found. That biological check — not just "the function returned
  without error" — is the real acceptance criterion here.

See Section 8 for which already-converted studies need a full re-run to pick
this up.

### 2c. Post-DecontX schema validation — neurodegen-commons (added 2026-08-25)

**Now a standing step of the conversion pipeline, not optional.** Every
study's `submit_decontx_<study>.sbatch` runs this immediately after
`verify_decontx_<study>.py`, against that study's freshly-written DecontX
output (`$WORKDIR/output/*.h5ad`, still on `/scratch` at that point — no
`/lts` copy needed for this in-line case). Purpose: the external
collaborator's own tooling (`neurodegen-commons`'s `pick_counts()`/
`pseudobulk()`, see Section 2a's cross-compatibility note) needs `donor`/
`cell_type`/`condition` obs roles to resolve and a genuine raw integer-count
matrix — this step catches a gap in either one right after DecontX, instead
of the collaborator finding it downstream.

- **Script**: `EXTERNAL_DATASETS/scripts/validate/run_commons_validate.py` —
  a thin wrapper around `neurodegen-commons`'s own `commons.h5ad_read.validate()`
  (imported as a library from the pinned checkout at
  `/ref/rmlab/software/azamat/tools/neurodegen-commons`, unmodified). Not the
  `python -m commons.cli h5ad validate` CLI directly — the CLI doesn't expose
  `validate()`'s `overrides=` parameter, which this pipeline needs (see below).
  Usage: `python run_commons_validate.py <study_id> <file1.h5ad> [file2.h5ad ...]`.
- **Env**: `/ref/rmlab/software/azamat/als_pipeline_env` (Python 3.11.8,
  anndata 0.12.19, numpy 2.4.6) — the same env every other conversion/DecontX
  step already uses. `validate()` only needs anndata+numpy, and this env
  already had both proven against a real run before this step existed, so no
  new environment was built for this.
- **Two HTCF gotchas that will bite you otherwise (same as every other step
  in this pipeline)**: run on a compute node via `sbatch`/`srun`, never the
  login node; and `/lts` is not accessible from compute nodes, so any file
  that doesn't already live on `/scratch` (e.g. validating an existing
  `processed/*.h5ad` standalone, outside the normal post-DecontX hook) must
  be copied to `/scratch` first, from the login node, before the job runs.
- **Per-study overrides**: `resolve_columns()` matches obs columns to the
  donor/cell_type/condition roles by alias, case-insensitively — most studies
  resolve with zero configuration. Where a study's real column either doesn't
  match any alias, or matches the WRONG one (a degenerate single-value ID
  that happens to alias-match), add an entry to `run_commons_validate.py`'s
  `OVERRIDES` dict (currently: `CrypticExon_ActaNeuropathol2023` ->
  `{"donor": "sample"}`, since that study's `sample_id` is a CELLxGENE
  dataset-level UUID with exactly 1 value across every cell — see Section 8a's
  entry for that study). Only add an override after checking the real obs
  columns — don't guess.
- **Real, permanent gaps vs. transient failures — the error-recording policy
  the user asked for explicitly (2026-08-25):** `validate()` is designed to
  never raise on a bad file — a missing/unresolvable column is reported as a
  string in its `problems` list, not an exception (confirmed by reading
  `commons/h5ad_read.py` directly, not assumed). The concrete risk flagged
  was: a study with no per-cell cell-type concept (e.g. an iPSC motor-neuron
  *culture*, not tissue with multiple cell types) will never resolve a
  `cell_type` column, which would otherwise permanently fail this gate for a
  reason no override can fix.
  **Design correction (2026-08-25, per explicit user direction):** an
  earlier version of this step called `validate()` with a trimmed
  `expected={'required_roles': ...}` so it would never even check `cell_type`
  for these studies. The user pushed back on this — it changes WHAT gets
  checked, i.e. modifies how `validate()` itself is invoked for a given
  study. The corrected design: `validate()` is ALWAYS called exactly the same
  way, with commons' own real default `required_roles` — no per-study
  `expected=` override exists anymore. The missing-cell_type problem is
  therefore genuinely detected and genuinely reported by `validate()` itself,
  every time. All reclassification happens strictly downstream, in
  `run_commons_validate.py`'s own code, after the real result comes back:
  `NOT_APPLICABLE_PROBLEMS` maps a study to the *exact* problem string
  `validate()` produces plus a reason; if that exact string appears in a raw
  `problems` list, it's moved into the report's `not_applicable_present`
  field and does NOT count against `passes_with_known_exceptions` — but it
  was still genuinely checked and genuinely failed, then relabeled, not
  pre-empted. This keeps `validate()` itself completely vanilla (matches the
  wrapper's own "does not modify neurodegen-commons in any way" principle)
  and keeps 100% of the applicability judgment as this conversion pipeline's
  own responsibility, per the user's framing. `KNOWN_EXCEPTIONS` is a
  separate, still-empty dict for a genuinely different case: a real,
  applicable failure accepted for some other reason (not "the check doesn't
  apply here").
  Currently populated in `NOT_APPLICABLE_PROBLEMS`: `Ho2021_CellSystems`,
  `DivergentC9_NatComms2023`, `HammellOneill2025_CellReports`,
  `NatureAging2024_ETneurons`, `Qki5_PNAS2024`, `Zelic2025_Immunity` — all 6
  confirmed 2026-08-25 via a full `obs_columns` dump (not just the alias-miss
  message) to have no cell-type-like column under any name. Add new entries
  here only after the same check — don't guess from the error string alone.
  As additional defensive insurance beyond `validate()`'s own no-raise
  contract, `run_commons_validate.py` also wraps the actual per-file call in
  its own try/except (`_validate_one()`) — if `validate()` ever crashes
  anyway (e.g. an unreadable file, or a future `commons` change that breaks
  this guarantee), that file's crash is recorded as its own report entry
  (`"crashed": true`, exception type+message+traceback) rather than losing
  the report for every other file already queued in the same batch.
- **Non-fatal by design**: the sbatch step is called as
  `... || echo "..."`, so an unexpected-problems exit (1) does NOT fail the
  overall DecontX job — DecontX itself already succeeded by the time this
  runs, and that result is still real and usable even if commons-schema
  validation finds a gap. A non-zero exit here is a signal for a human/
  session to go read the report, not evidence the conversion failed.
- **Output**: `commons_validate_report.json`, written next to the first input
  file — so, directly inside `$WORKDIR/output/` on `/scratch`, the same
  directory the h5ad(s) already live in for the normal post-DecontX hook.
  Because it shares that directory, it rides along automatically as long as
  Section 5's scratch->lts copy-back is done at the directory level (as
  Section 5 now requires) rather than as an enumerated `*.h5ad` copy — no
  separate step needed. It is now part of a study's expected `processed/`
  output, same status as `conversion_log.md` (Section 7's directory layout
  updated accordingly). Don't leave it stranded on `/scratch` uncopied.
- **Retroactive catch-up (2026-08-25)**: the 8 already-DecontX'd studies in
  scope as of this writing (Section 8's list) predate this step existing.
  `CrypticExon_ActaNeuropathol2023` was already spot-checked earlier
  (2026-08-18, all 4 files pass) and is what this step's design was validated
  against before being made standing policy. The remaining 7
  (`Brain2025_Multiome`, `DivergentC9_NatComms2023`,
  `HammellOneill2025_CellReports`, `Ho2021_CellSystems`,
  `NatureAging2024_ETneurons`, `Qki5_PNAS2024`, `Zelic2025_Immunity`) were run
  through it for the first time this same day as a one-time catch-up against
  their already-converted `/lts` output (not a full DecontX re-run) — see
  `CHANGELOG.jsonl` for the actual results.

## 3. Per-study source data inventory (verified against actual files on `/lts`)

Base path for all: `/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS/studies/<study_id>/raw/`

### Ho2021_CellSystems (scRNA-seq, ddSEQ + 10x)
Flat files directly in `raw/` (no subfolder):
`GSE138121_BatchA_ddSEQ_UMIcounts.csv.gz`, `GSE138121_BatchB1_ddSEQ_UMIcounts.csv.gz`,
`GSE138121_BatchB2_ddSEQ_UMIcounts.csv.gz`, `GSE138121_BatchC_ddSEQ_UMIcounts.csv.gz`,
`GSE138121_BatchD_ddSEQ_UMIcounts.csv.gz`, `GSE138121_BatchE_10X_UMIcounts.csv.gz`,
`GSE138121_BatchF_10X_UMIcounts.csv.gz`, `GSE138121_CellBarcodes.csv.gz`.
Each Batch file is a gene x cell UMI count CSV (genes as rows). Batches A-D are ddSEQ,
E-F are 10x — same conversion path (`pd.read_csv` -> `AnnData(X=counts.T)`), but note
the two platforms in `adata.obs["batch_platform"]`.

### Zelic2025_Immunity (scRNA-seq + bulk RNA-seq)
- `raw/GSE287439/GSE287439_RAW.tar` -> per-GSM `*_filtered_feature_bc_matrix.h5`
  (10x CellRanger format, e.g. `GSM8745655_triculture_s1_filtered_feature_bc_matrix.h5`)
  — read with `sc.read_10x_h5`.
- `raw/GSE287257/GSE287257_RAW.tar` -> same pattern, e.g.
  `GSM8742363_29_control_filtered_feature_bc_matrix.h5`
- `raw/GSE287569/GSE287569_RAW.tar` -> same pattern, e.g.
  `GSM8748142_SOD1_s1_filtered_feature_bc_matrix.h5`
- `raw/GSE287256/GSE287256_ALS_bulkRNAseq_results_bulk_counts_normalized.csv.gz` -
  **bulk RNA-seq, route to Parquet table, not h5ad.**

### HammellOneill2025_CellReports (snRNA-seq)
`raw/GSE271156/GSE271156_RAW.tar` -> per-GSM **nested** `*_count_matrix.tar.gz`
(e.g. `GSM8370898_JR9_count_matrix.tar.gz`) — each of these inner tarballs must be
extracted again to reach the 10x triplet/h5 inside. Handle recursively.

### Lall2025_CellStemCell (snRNA-seq + bulk RNA-seq)
- `raw/GSE255605/GSE255605_RAW.tar` -> per-GSM
  `*_filtered_genesummed_mtx.csv.gz` (e.g.
  `GSM8075906_b1.EDi029-A.00_filtered_genesummed_mtx.csv.gz`) - gene x cell CSV,
  ALREADY FILTERED by original authors (note this in conversion_log, do not re-filter).
- `raw/GSE255602/GSE255602_Bulk_RNAseq_all_samples_salmon_counts.csv.gz` -
  **bulk RNA-seq (Salmon), route to Parquet table.**
- Note: GSE255606 was found to be a pure superseries container (re-lists GSE255602's
  and GSE255605's GSMs with no unique files of its own) - already excluded from
  download; do not look for it.

### NatureAging2024_ETneurons (snRNA-seq)
`raw/GSE226753/GSE226753_RAW.tar` -> single file
`GSM7083181_MotorCortex_02202018.ICA_res0.1_mingenes400.raw.dge.txt.gz` - plain-text
digital gene expression (DGE) matrix, gene x cell. Only 1 sample in this study.

### pTDP43_PNAS2025 (snRNA-seq + snATAC-seq, multiome)
`raw/GSE212630/GSE212630_RAW.tar` -> per-GSM PAIRED files:
RNA: `*_filtered_feature_bc_matrix.h5` (10x, e.g. `GSM8735053_Control-1_filtered_feature_bc_matrix.h5`)
ATAC: `*_atac_fragments.tsv.gz` + `*_atac_fragments.tsv.gz.tbi.gz` (e.g.
`GSM8735103_TDPhigh-7_atac_fragments.tsv.gz`).
**This is the multiome study -> build `.h5mu` with `mod={"rna": ..., "atac": ...}`.**
52 GSMs total (RNA+ATAC pairs). Sample groups by filename prefix: Control, TDPneg, TDPhigh
(refer to `samples.json` normalized fields for the full genotype/group mapping).

### Qki5_PNAS2024 (scRNA-seq + 2x bulk RNA-seq)
- `raw/GSE267791/` -> flat 10x triplet: `GSE267791_barcodes.tsv.gz`,
  `GSE267791_features.tsv.gz`, `GSE267791_matrix.mtx.gz` — read with `sc.read_10x_mtx`
  (single combined dataset, not per-GSM).
- `raw/GSE218824/GSE218824_RAW.tar` -> per-GSM pairs: `*.expr.txt.gz` (bulk RNA-seq
  plain-text counts, e.g. `GSM6757185_hiPSC-MNs-NC1.expr.txt.gz`) +
  `*_AS_events.tar.gz` (alternative-splicing event tables - keep as a separate
  supplementary table, not part of the main count matrix).
  **Route `.expr.txt.gz` files to Parquet bulk table; keep AS-events tarballs
  unpacked into a `processed/qki5_as_events/` folder as-is (splicing tables, not
  expression counts).**
- `raw/GSE218820/GSE218820_RAW.tar` -> same pattern as GSE218824 but OPC samples
  (e.g. `GSM6757086_OPC-NC1.expr.txt.gz` + `GSM6757086_OPC-NC1_AS_events.tar.gz`).

### Schweingruber2025_NatComms (scRNA-seq, 1415 samples)
`raw/GSE226482/GSE226482_counts.txt.gz` and `raw/GSE226482/GSE226482_rpkms.txt.gz` -
plain-text gene x sample tables covering all 1415 samples in ONE file each (not
per-GSM tars). Use `_counts.txt.gz` as the primary matrix (raw counts); keep
`_rpkms.txt.gz` as an alternate normalized layer (`adata.layers["rpkm"]`).

### DivergentC9_NatComms2023 (snRNA-seq + bulk RNA-seq + bulk ChIP-seq)
- `raw/GSE219280/GSE219280_RAW.tar` -> per-GSM sets of 4 files each:
  `*_cellBender_corrected_filtered.h5` (ALREADY FILTERED/corrected - use as primary),
  `*_raw_barcodes.tsv.gz`, `*_raw_features.tsv.gz`, `*_raw_matrix.mtx.gz` (the
  pre-cellBender raw triplet - keep as `adata.layers["raw_precorrection"]` if you
  want the true unfiltered counts, since the cellBender file IS the "filtered"
  matrix here, not a truly raw one). Example prefix: `GSM6781906_snRNA_C9ALS_A1_FrontalCortex`.
- `raw/GSE219278/` -> flat files (not tarred): `GSE219278_allSamples_rsem_genes_results_counts_annotated.tsv.gz`
  and `..._TPM_annotated.tsv.gz` - **bulk RNA-seq (RSEM), route to Parquet table**
  (use counts as primary, TPM as an alternate column set/second table).
- `raw/GSE219277/GSE219277_RAW.tar` -> **bulk H3K27ac ChIP-seq** - per-sample pairs
  of bigWig (`.bw`) + broadPeak table (`.tsv.gz`), naming pattern
  `GSM<id>_ChIPseq_<genotype>_<donor>_<celltype>_H3K27ac_{1M.bw|broadPeak.tsv.gz}`,
  e.g. `GSM6781685_ChIPseq_C9ALS_A10_Astrocytes_H3K27ac_1M.bw` +
  `GSM6781685_ChIPseq_C9ALS_A10_Astrocytes_H3K27ac_broadPeak.tsv.gz` (verified via
  `tar -tf` against the actual archive - submit-to-completion took ~10 min on this
  filesystem for the 12.5GB archive, including Slurm queue wait). Cell types observed in the first
  10 entries: Astrocytes, Microglia, Neurons, OligoLineage. **Leave in native
  format** per Section 2 - do not attempt a matrix conversion as part of this pass.

### Brain2025_Multiome (already h5ad, CELLxGENE)
`raw/Brain dataset.h5ad`, `raw/Spinal cord dataset.h5ad` - already valid AnnData.
No format conversion needed. Just copy into `processed/` and confirm/attach the
normalized `obs` columns (organism, tissue, disease, cell_type, assay, sex, donor_id
are already present as CELLxGENE ontology-annotated `obs` columns - map field NAMES
to match the schema used by the rest of the collection, don't duplicate).

### CrypticExon_ActaNeuropathol2023 (already h5ad, CELLxGENE, 4 files)
`raw/Frontal cortex samples from C9-ALS_ C9-ALS_FTD and age matched control brains.h5ad`,
`raw/Frontal cortex samples from C9-FTD and age matched control brains.h5ad`,
`raw/Occipital cortex samples from C9-ALS_ C9-ALS_FTD and age matched control brains.h5ad`,
`raw/Occipital cortex samples from C9-FTD and age matched control brains.h5ad`.
Same handling as Brain2025_Multiome - already valid h5ad, just copy + confirm obs schema.

### Pineda2024_Cell — FULLY ALIGNED, both arms ready (updated 2026-08-28)
The alignment role's CellRanger pipeline has finished **all 154 samples** —
149 human + 5 mouse (C57BL/6 controls). All have real, QC-verified
`filtered_feature_bc_matrix.h5`/`raw_feature_bc_matrix.h5` output at
`studies/Pineda2024_Cell/raw/counts/<SRR>/` (verified by directory count —
154/154 — and `metrics_summary.csv` content for every sample, not just job
exit status; see `CHANGELOG.jsonl` 2026-08-28T09:00 for the human arm and
the entries following it for the mouse arm). **Conversion may start on the
full study now** — build the standard per-study `convert_Pineda2024_Cell.py`
following this file's usual conventions (Section 2a/4), reading each SRR's
`filtered_feature_bc_matrix.h5` and attaching `samples.json`'s normalized
metadata joined on `sample_id`.
**Species split, do not skip:** `samples.json`'s `normalized.organism` field
distinguishes the 149 `Homo sapiens` samples from the 5 `Mus musculus`
samples (SRR27867712-716) — route to separate `adata`/species-specific
handling (different gene symbol namespace, different reference build:
GRCh38-2024-A for human, mm10-2020-A for mouse) rather than concatenating
into one AnnData with mixed-species genes. The mouse samples' QC profile is
real but genuinely different from the human ones (lower Fraction Reads in
Cells, ~29-38% vs ~78-83% for human; higher Reads Mapped Antisense to Gene,
~46-53% vs ~5-19% for human) — consistent across all 5 mouse samples, so
treat this as an expected mm10/mouse-cortex characteristic to be aware of,
not a data-quality flag to chase down.

### OFC_APA_CellGenomics2025 — NOT YET IN raw/
FASTQ-only, no processed matrices exist yet. FASTQ is now genuinely complete
(46/46 runs, resolved 2026-08-26 — see `ALIGNMENT_INSTRUCTIONS.md`), but real
alignment has not been submitted for this study through the pipeline yet as
of this writing (only `Pineda2024_Cell` has real alignment runs so far). Do
not attempt conversion for this study until FASTQ->count-matrix alignment
(CellRanger) has actually produced count matrices — check
`studies/OFC_APA_CellGenomics2025/raw/counts/` directly rather than assuming
from this note, since alignment progress moves independently of this doc.

## 4. Metadata attachment

Every study already has a `samples.json` with a `normalized` sub-object per sample
record (fields: `study_id`, `accession`, `sample_id` [GSM], `assay_type`,
`sample_source`, `organism`, `cell_line_or_donor`, `genotype`, `disease_status`,
`tissue_or_cell_type`, `timepoint_or_age`, `treatment`, `sex`, `platform`, `batch`,
`file_names`, `source_doi_or_pmid`, plus `extra_disease_onset_site`/`extra_chip_antibody`
where applicable). There is also a collection-wide `all_samples.tsv` at
`/lts/.../EXTERNAL_DATASETS/all_samples.tsv` with one row per sample across the
whole collection (1,976 rows).

When building each `adata.obs`, join by `sample_id` (GSM accession) extracted from
the source filename (regex `GSM\d+` at the start of each filename) against
`samples.json`'s `gsm` field, and copy across the `normalized` block's fields as
`adata.obs` columns using the SAME column names given above — this keeps every
converted object's metadata schema identical and matches the master
`all_samples.tsv`, so cross-study queries stay consistent. **Also copy the
canonical vocabulary columns when present — see Section 4a's conversion
instruction below; they are not part of the original field list above because
they were added later, but they follow the exact same copy-as-obs-column rule.**

### 4a. Canonical vocabulary columns (added 2026-09-11)

Three fields above — `disease_status`, `tissue_or_cell_type`, `genotype` — have real
spelling/format drift across studies (each study was normalized independently, no
shared controlled vocabulary was ever enforced; e.g. `"Control"`/`"control"`/`"CTL"`,
or `"Cerebellum; Cerebellum"` vs `"Cerebellum"` vs `"Cerebellum"` — same value, three
formats). This is now fixed going forward with **additive, never-replacing** canonical
columns, all in `all_samples.tsv` and every study's `samples.json`:

- `disease_status_canonical` — canonical form of `disease_status`. Original column
  untouched.
- `tissue` + `cell_type` — `tissue_or_cell_type` is SPLIT, not just canonicalized,
  since many values genuinely mix two different kinds of information (a body region
  *and* a sorted cell population, e.g. `"motor cortex; oligodendrocyte lineage cells
  (NeuN-SOX10+)"` → `tissue="motor cortex"`, `cell_type="oligodendrocyte lineage
  cells (NeuN-SOX10+)"`). Original `tissue_or_cell_type` column untouched.
- `genotype_canonical` — canonical form of `genotype` (in progress as of this
  writing — see `CHANGELOG.jsonl` 2026-09-11T17:00 for current status before relying
  on it existing for every study).

**Reference tables** (dataset collection root, `download_metadata`-owned, growing
over time): `vocabulary/disease_status_canon.tsv`, `vocabulary/tissue_or_cell_type_canon.tsv`,
`vocabulary/genotype_canon.tsv` — each a `raw_value → canonical_value` lookup (the
tissue one also carries `tissue`/`cell_type` split columns). Human-readable rationale
for every non-mechanical decision made so far lives in `vocabulary/CHANGES.md` (and
`vocabulary/genotype_CHANGES.md` once that pass lands).

**Standing instruction for `download_metadata` — every future study, not a one-time
pass:** when normalizing a new study's `disease_status`/`tissue_or_cell_type`/
`genotype` values, check each raw value against the matching `vocabulary/*_canon.tsv`
table before writing the canonical column(s):
- **Matches an existing entry** (exact, or the same modulo case/whitespace/
  separator/duplicate-join formatting) → apply that canonical value automatically,
  no review needed.
- **Doesn't match anything in the table** → this is a genuinely new term. Do **not**
  silently guess a mapping and do **not** silently leave it unmapped — ask the user
  directly for the classification, the same standard used for the 2026-09-11
  backfill. Once decided, add the new entry to the vocabulary table permanently (and
  a line to the relevant `CHANGES.md`) so the same term never needs asking again for
  any future study.
- **Never auto-merge look-alike values that may represent a real distinction** —
  concrete examples already found: `"Non-Neurological Control"` vs `"Other
  Neurological Disorders"` vs plain `"Control"` are different control populations,
  not spelling variants; `"FUS_KO"` (CRISPR knockout) vs `"FUS Knockdown"` (siRNA/
  shRNA knockdown) are different techniques; `"FUS_P525L_homozygous"` vs
  `"...heterozygous"` — zygosity is often the entire point of the experiment;
  `"motor cortex"` (unspecified) vs `"lateral motor cortex"` vs `"medial motor
  cortex"` are different specificity levels, not duplicates. When a new value looks
  similar to an existing canonical entry, that similarity is a reason to ask, not a
  reason to merge.
- A bare/uninterpretable raw value (e.g. a number with no label) is a data-quality
  bug, not a vocabulary gap — investigate and flag it separately rather than forcing
  it into the canonicalization table.

**Standing instruction for `conversion` — every future study:** when a study's
`samples.json` carries the canonical columns (`disease_status_canonical`, `tissue`,
`cell_type`, `genotype_canonical`), copy them into `adata.obs` exactly like every
other normalized field in Section 4, same column names, same join-by-`sample_id`
mechanism — nothing special about how they're written, they're just more fields in
the `normalized` block by the time conversion reads it. Two things to actually
check, not assume:
- **Presence is conditional, check before assuming.** Not every study has all four
  columns yet (`genotype_canonical` in particular is still rolling out as of
  2026-09-11 — see `CHANGELOG.jsonl`). Copy whichever of the four are actually
  present for that study; don't fail or block a conversion because one is missing,
  and don't fabricate a value for one that isn't there.
- **Already-converted studies are not retroactively migrated.** If you're re-running
  conversion on a study for an unrelated reason (a bug fix, a DecontX re-run, etc.)
  and its `samples.json` now has canonical columns it didn't have at the object's
  last conversion, pick them up in that pass — this is the natural, opportunistic
  way already-converted studies catch up, exactly as described when this system was
  designed. Don't go out of your way to force a re-conversion of every already-done
  study purely to backfill these columns; that's explicitly out of scope.

**Standing instruction for `verification` — every future study (updated
2026-09-18, scope narrowed to the download/metadata side only — see
`PROTOCOL.md` Section 2b, `downstream_verification` now owns checking
`conversion`'s output):** when verifying a newly-normalized study's raw
metadata, check the canonical columns in `samples.json`/`all_samples.tsv` as
part of the normal pass, not as a separate one-off:
1. `disease_status_canonical`/`tissue`/`cell_type`/`genotype_canonical` are present
   for every sample record that has a non-null source value (or explicitly absent
   with a documented reason, never silently missing).
2. Spot-check a handful of the study's canonical values directly against the
   `vocabulary/*_canon.tsv` tables — confirm the mapping applied is actually the one
   on record, not a fresh ad hoc decision that bypassed the table.
3. Confirm no danger-zone-style over-merge happened — if a new study introduces a
   value that looks like it was folded into an existing canonical bucket it probably
   shouldn't share (see the examples above), flag it rather than assuming
   `download_metadata` got it right.
4. Confirm the original raw columns (`disease_status`, `tissue_or_cell_type`,
   `genotype`) are still present and byte-for-byte unchanged — these additive
   columns must never replace or overwrite the source values.

**Standing instruction for `downstream_verification` — every future study
(added 2026-09-18):** for a newly-converted `.h5ad`, confirm `adata.obs`
actually carries whichever canonical columns `samples.json` has for that
study (per `conversion`'s Section 4a instruction above) — a study with
canonical metadata whose converted object doesn't expose it in `.obs` is a
real gap, not a non-issue, since it means downstream consumers filtering on
the canonical fields silently miss that study. This is one item within this
role's broader conversion-output-checking scope, not the whole of it — see
`PROTOCOL.md` Section 2b for the full checklist (structural integrity,
DecontX correctness, and separately, alignment output QC).

**PERMANENT EXCEPTION — `Brain2025_Multiome` and `CrypticExon_ActaNeuropathol2023`
are excluded from `cell_type` backfill, added 2026-09-28, do not revisit without a
fresh user decision:** these two studies' `samples.json` records do not use the
standard per-GSM `normalized` block at all — they use a different, CELLxGENE-native
record shape (top-level `organism`/`tissue`/`disease`/`cell_type`/`assay` lists
copied from the CELLxGENE dataset's own metadata), and each record represents a
whole multi-donor deposited file, not one biological sample. A single file
genuinely contains many real cell types at once (10 for Brain2025_Multiome, 6 for
CrypticExon), so there is no single correct scalar `cell_type` value that could ever
be written for "this record" — forcing one would be wrong, not just incomplete.
The correct place for this information is exactly where it already lives: a real,
populated, per-cell `cell_type` column already exists in both studies' `.h5ad`
`adata.obs` (the native CELLxGENE per-cell annotation), which for
Brain2025_Multiome and CrypticExon_ActaNeuropathol2023 is *also* the cluster-label
input their DecontX runs actually used. **Do not write anything to the `cell_type`
obs column for these two studies' `.h5ad` files under any circumstance** — a
same-named write would silently overwrite that real annotation with either nulls
or a wrong-shape value (a list of 6-10 labels, not one). `disease_status_canonical`
and `genotype_canonical` are correctly out of scope for the same structural reason
(no `normalized` block exists to read from). `tissue` is a narrower, different case
— each file *does* have one clean tissue value (`"primary motor cortex"` /
`"occipital cortex"`) and could plausibly be backfilled later, but that is a
separate decision, not yet approved, and not part of this exception's cell_type
carve-out.

## 5. Execution constraints (HTCF-specific — read before writing job scripts)

- `/lts/rmlab` is **read-only on Slurm compute nodes** (confirmed: mounted `rw` on
  the login node, `ro` on compute nodes via `mount` check). All conversion jobs
  MUST read raw input from `/lts` (read is fine) but WRITE output to a scratch
  directory, e.g. `/scratch/rmlab/rmlab_shared3/<user>/als_conversion_work/`.
  After a study's conversion succeeds and is verified, copy the output back to
  `/lts/.../studies/<study_id>/processed/` via a command run on the LOGIN NODE
  (not inside the Slurm job), then delete the scratch copy.
  **Copy the whole scratch output directory (`cp -r`/`rsync -a` the directory
  itself, not an enumerated `*.h5ad` file list) — added 2026-08-26 because
  `commons_validate_report.json` (Section 2c) now lands in that same
  directory alongside the h5ad(s), and a file-by-file copy habit from before
  that step existed will silently drop it.** This applies to every scratch
  output directory in this pipeline going forward, not just DecontX's.
- Batch work per study (or a small group of small studies) — do not submit one
  giant job for the whole collection. This also matches the project's existing
  "download in batches, clean up scratch after" convention.
- For the large multiome files (pTDP43 ~50GB raw, DivergentC9 ~11GB raw) request
  enough memory for the AnnData/MuData objects to fit comfortably in RAM during
  conversion — plan for at least 3-4x the raw file size as a working-memory budget
  for sparse-matrix construction, and request Slurm `--mem` accordingly per job.
- `tar -tf` on the larger archives on this filesystem is slow: listing
  `GSE219277_RAW.tar` (12.5GB) took ~10 minutes submit-to-completion; multiple shorter attempts (30 min
  and under) on `GSE212630_RAW.tar` (51.5GB, pTDP43) and other large tars timed out
  before returning a listing (only a partial head via a truncated read succeeded).
  Do not assume tar listing is instant; either extract directly with `tar -xf`
  (no separate list step) or budget a generous time limit (45+ min) if a listing
  is needed first.

## 6. Explicitly out of scope for this pass

- Do NOT attempt cross-study integration/batch-correction (e.g. building one
  combined AnnData across studies) - each study stays its own file.
- Do NOT attempt FASTQ alignment for OFC_APA_CellGenomics2025 or Pineda2024_Cell -
  those need CellRanger/STARsolo + reference genome setup, a separate task.
- Do NOT build a ChIP-seq peak-count matrix for DivergentC9's GSE219277 unless
  specifically asked - leave as native bigWig/narrowPeak.

## 7. Suggested directory output layout (per study)

```
studies/<study_id>/
  raw/                      <- existing, do not modify
  processed/
    <study_id>.h5ad          (or .h5mu for multiome, or .parquet+.tsv for bulk)
    conversion_log.md
    commons_validate_report.json   <- droplet studies only, added by Section 2c;
                                       copy back alongside the h5ad(s), don't
                                       leave it stranded on /scratch
  samples.json              <- existing, already has normalized metadata
  README.md                 <- existing
```

## 8. Re-running previously converted studies to add DecontX (added 2026-07-27)

DecontX support (Section 2b) was added after several studies were already
converted and (in some cases) already structurally `verified`. These need a
**full re-run** (not a patch/append to the existing file) to add the new
`layers["decontx_corrected"]` and `obs["decontx_contamination"]` fields.

**Needs a re-run** (already `converted`, droplet-based, DecontX applies):
- `Zelic2025_Immunity` — all 3 scRNA h5ad, run DecontX on each independently
  (don't merge across series).
- `HammellOneill2025_CellReports`
- `NatureAging2024_ETneurons`
- `Qki5_PNAS2024` — the scRNA h5ad only; its 2 bulk Parquet/TSV tables and
  AS-events tarballs are unaffected, don't touch them.
- `Brain2025_Multiome` — RNA side of both h5ad files.
- `CrypticExon_ActaNeuropathol2023` — all 4 h5ad files.
- `pTDP43_PNAS2025` — the RNA-side h5ad already converted; re-run to add
  DecontX. The ATAC/`.h5mu` build remains separately blocked per
  `PTDP43_ATAC_BLOCKED.md` — unrelated to this.
- `DivergentC9_NatComms2023` — once its existing empty-droplet bug fix (see
  `conversion_process.md`) is confirmed correct and copied to `/lts`, fold
  DecontX into that same corrected run rather than converting twice.

**Do NOT re-run for DecontX** (already converted, but DecontX doesn't apply
here at all):
- `Schweingruber2025_NatComms` — Smart-seq2 plate-based, per
  `AMBIENT_RNA_RAW_DATA_AUDIT.md`'s `NOT_APPLICABLE` classification. Leave as-is.
- Any study's bulk RNA-seq/ChIP-seq companion tables (Zelic's, Qki5's,
  DivergentC9's, Lall's) — DecontX is a single-cell/nucleus RNA-expression-matrix
  method, not applicable to bulk data.

**Not yet converted — build DecontX in from the start once conversion
succeeds** (no re-run needed later, just don't skip this step on the first
successful run):
- `Ho2021_CellSystems` — currently failing repeatedly on an unrelated join bug;
  once that's fixed, include DecontX in that same first successful run.
- `Lall2025_CellStemCell`'s snRNA arm — currently blocked on unrecoverable
  gene row order; if/when that's ever resolved, DecontX applies then.
- `OFC_APA_CellGenomics2025` — FASTQ-only, out of scope until CellRanger
  produces a matrix at all (Section 6). `Pineda2024_Cell` is no longer in
  this out-of-scope group — it now has real `raw_feature_bc_matrix.h5`
  output for all 154 samples (see Section 3), so build DecontX in from its
  first successful conversion run like any other study, not a later re-run.

Per `PROTOCOL.md`: log each re-run as its own `converted` changelog entry,
explicitly noting "DecontX re-run" so `verification` knows to re-verify a study
it may have already marked `verified` — its existing structural pass didn't
see this new content. Update `conversion_status.json` accordingly; a study
going from `converted` back to `converting` for a re-run is expected here, not
a regression.

### 8a. THIRD re-run needed: batch-aware DecontX (added 2026-07-29)

An external collaborator flagged (relayed by the user) that DecontX must be
run per-capture, not pooled across an entire study's concatenated object — see
Section 2b's new `batch` parameter bullet for the full technical explanation
and the `sample_id`-as-capture-proxy default. Every study whose DecontX pass
(this rollout, per this section) ran on a multi-`sample_id` object needs
**yet another** full re-run to add batch-splitting, regardless of whether it
was already re-run once for DecontX itself:

- `HammellOneill2025_CellReports` (6 samples), `Ho2021_CellSystems` (25
  samples), `Qki5_PNAS2024` scRNA h5ad (16 samples) — these three already
  completed their DecontX re-run (Slurm jobs 44076834/44077166/44077245,
  logged 2026-07-28) with **no** batch argument. Their `decontx_corrected`/
  `decontx_contamination` values are contaminated (no pun intended) by the
  cross-capture pooling bug and must be redone. `verification`'s pending
  re-verification of these three (already flagged as owed, per Section 8
  above) should wait for this second re-run rather than verify the current
  un-batched output.
- `NatureAging2024_ETneurons` — already re-run, but has only 1 distinct
  `sample_id`, so its existing output is unaffected by this bug. No further
  action needed for this reason (its DecontX re-run from Section 8 stands).
- `Zelic2025_Immunity`, `Brain2025_Multiome`, `CrypticExon_ActaNeuropathol2023`,
  `DivergentC9_NatComms2023` — as of 2026-07-29 these are still actively
  locked/in-progress for their Section 8 DecontX re-run. **Do not let these
  finish and copy to `/lts` without the `batch` argument** — add it now, before
  these in-flight jobs complete, rather than finishing them un-batched and
  needing a third pass. If any have already finished and been copied to
  `/lts` by the time you read this, treat them the same as the three bulleted
  above (redo with `batch`).
- `pTDP43_PNAS2025` — still deferred (per Section 8 above, waiting on the
  `pTDP43_group` metadata re-join); when it's finally run, include `batch`
  from the start, no separate pass needed.

Use the same changelog convention as Section 8: log each of these as its own
`converted` entry, explicitly noting "batch-aware DecontX re-run" (distinct
from a plain "DecontX re-run" note) so the record shows which pass actually
has correct per-capture contamination estimates.

## 9. Bulk RNA-seq harmonization to a shared format (added 2026-08-21)

**Why this section exists**: Section 2 already says bulk RNA-seq routes to
"Parquet (primary) + plain TSV" — but that policy has never actually been
executed for any bulk study. Every bulk study/arm in the collection is still
exactly as its own paper's authors deposited it on GEO, and those deposits
are genuinely heterogeneous — confirmed directly: `Dunker2021_GSE162644` is
`.csv.gz` with versioned Ensembl IDs (`ENSG00000223972.5`); `Krug2017_GSE85398`
is tab-delimited *Drosophila* gene symbols; `Klim2019_GSE121569` has FOUR
different files (`_raw_counts.csv.gz`, `_dexseq-all.csv.gz`,
`_combined.dexseq.txt.gz`, `_category_als_vs_control_all.csv.gz`) with no
single obvious canonical matrix. This section makes the target format concrete
enough to actually be comparable across studies, not just "some Parquet file
per study."

**Scope**: every bulk-RNA-seq study/arm currently `out_of_scope` in
`conversion_status.json` — this is the full list you should work through, not
just a sample: the bulk companion arms of `Zelic2025_Immunity` (GSE287256),
`Lall2025_CellStemCell` (GSE255602), `Qki5_PNAS2024` (GSE218824/GSE218820),
`DivergentC9_NatComms2023` (GSE219278 — **not** GSE219277's ChIP-seq, which
stays native bigWig/broadPeak per Section 6, no matrix conversion), and
`HammellOneill2025_CellReports` (GSE272624/GSE272626/GSE308462, 815 samples —
this one is also flagged CRITICAL by verification, prioritize it); plus the
18 "cross-reference" bulk studies (`Klim2019_GSE121569`, `Tam2019_GSE122647`,
`Tam2019_GSE124439`, `Dafinca2020_GSE147544`, `Dunker2021_GSE162644`,
`Asano2025_GSE283507`, `Bryce-Smith2025_GSE296714`, `Ma2025_GSE299997`,
`GSE310722_dataset`, `Krug2017_GSE85398`, `Cho2020_GSE126044`,
`Jung2019_GSE135222`, `GSE164690_dataset` — scRNA, not bulk, skip here —,
`Baruch2025_GSE289744`, `Lim2022_GSE180928` — snRNA, not bulk, skip here —,
`GSE329677_dataset`, `Dumitriu2016_GSE68719`, `Liu2019_CellReports_GSE126543`
[bulk RNA arm only — its ATAC arm needs its own decision, not covered here]);
plus the 8 Tier-2 studies added 2026-08-20 (`Conlon2018_GSE116622`,
`Catanese2021_GSE168831`, `Szewczyk2025_GSE272827`, `Zimyanin2026_GSE276214`,
`Korada2025_GSE300423`, `Prudencio2015_GSE67196`, `Krach2018_GSE76220`,
`Kapeli2016_GSE77702`) — these aren't in `conversion_status.json` at all yet,
add them when you start.

**Target format** (per bulk series — one series can span multiple GEO
accessions if they're genuinely one experiment, e.g. `HammellOneill`'s three):

1. **Orientation: samples as rows, genes as columns.** Matches Section 2's
   existing "sample x gene matrix" wording, and matches `pydeseq2`'s expected
   input shape (relevant since `neurodegen-commons`, a downstream consumer of
   this collection, uses `pydeseq2`) — do not transpose a study whose raw
   deposit happens to already be genes-as-rows without converting it.
2. **Gene ID column: Ensembl gene ID, version suffix stripped**
   (`ENSG00000223972`, not `ENSG00000223972.5`) as the canonical column key.
   Versions drift across GENCODE releases and silently break joins across
   studies that used different annotation versions — stripping them is a
   real information loss, so also keep a `gene_id_versioned` companion column
   recording the original value, don't just discard it.
   - **Non-human studies (`Krug2017_GSE85398`, Drosophila) keep native gene
     IDs (FBgn), not silently ortholog-mapped to human by us.**
     `neurodegen-commons` already does this mapping on their own side
     (confirmed via their Reprocessing Methods sheet: "Fly FBgn -> human via
     Ensembl ortholog map") — duplicating it here risks two different mapping
     tables silently disagreeing. Just make sure `organism` is correctly
     populated in the metadata companion file (Section 4) so it's obvious
     which studies need that step downstream.
   - Symbol-to-ID or ID-to-symbol lookups are a separate small companion
     table if genuinely needed, not embedded in the counts table itself.
3. **Values: raw/deposited counts as the primary table.** Never substitute
   a normalized value (TPM, RPKM, DESeq2-normalized) for counts — if a
   deposit provides both, counts is primary and the normalized values go in
   a clearly-named second table (same pattern `DivergentC9_NatComms2023`'s
   existing bulk RNA entry in Section 3 already uses: "counts as primary,
   TPM as an alternate column set/second table").
4. **When a study's raw deposit isn't already one clean matrix** (the
   `Klim2019_GSE121569` case above): pick the plainest raw gene-count matrix
   as the canonical `_counts` table (here, `_raw_counts.csv.gz`, not the
   DEXSeq output or the pre-computed contrast file). Don't silently drop the
   others if they carry real information a plain gene-count matrix doesn't —
   `_dexseq-all.csv.gz`/`_combined.dexseq.txt.gz` are exon/splicing-level
   quantification, which may be independently useful given this collection's
   existing interest in splicing (see the DecontX/ambient-RNA and
   `neurodegen-commons` cryptic-splicing threads) — keep as a separate
   `_splicing` output rather than discarding, and note the choice in
   `conversion_log.md`. `_category_als_vs_control_all.csv.gz` (a
   pre-computed contrast, not raw data) does not need conversion at all —
   note in the log that it was intentionally left as-is.
5. **Metadata stays in a companion file, not embedded in the counts table.**
   Mirrors how `.h5ad` keeps `X` (matrix) and `obs` (metadata) conceptually
   separate even though physically one file — Parquet/TSV don't have that
   built in, so split into two files instead. The metadata file is
   `sample_id`-indexed, using the same normalized schema already established
   for single-cell (`all_samples.tsv`'s columns — study_id, disease_status,
   genotype, tissue_or_cell_type, etc.), joined the same way (Section 4).

**Output naming and path** — same `studies/<study_id>/processed/` directory
`conversion` already owns for single-cell output (Section 7), no new root:

```
studies/<study_id>/processed/
  <study_id>_bulk_<series_tag>_counts.parquet
  <study_id>_bulk_<series_tag>_counts.tsv.gz
  <study_id>_bulk_<series_tag>_metadata.tsv
  <study_id>_bulk_<series_tag>_splicing.parquet     <- only if the deposit has real splicing/exon-level output (Section 9.4)
  <study_id>_bulk_<series_tag>_normalized.parquet   <- only if the deposit has TPM/RPKM/etc alongside counts
```

`<series_tag>` = the GEO accession the series came from when a study has more
than one bulk arm mapped to different accessions (e.g.
`HammellOneill2025_CellReports_bulk_GSE272624_counts.parquet`), or omitted
when there's only one bulk series for the study. **One file pair per study
series, never merged across studies** — same one-file-per-study principle
Section 6 already enforces for single-cell; a cross-study combined bulk
matrix is a deliberate downstream analysis step, not part of this conversion
pass, same reasoning as Section 6's existing single-cell rule.

**Every converted bulk series still needs a `conversion_log.md` entry**
(Section 2's existing requirement) documenting: source file(s) used, which
file was chosen as canonical if the deposit had more than one (Section 9.4),
gene ID scheme confirmation, and organism. Flag to `verification` via the
changelog once each series is done, same as any other conversion.
