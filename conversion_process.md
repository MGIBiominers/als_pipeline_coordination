# ALS Pipeline — Conversion Process Log

Tracks what was done in each phase of the format-conversion pass driven by
`PIPELINE_INSTRUCTIONS.md`. Companion to `CATALOG.md` (collection-level status)
and `METADATA_QC_FLAGS.md` (metadata QC findings), both now at the coordination root (`/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/`), not the dataset collection.

Scope for this pass (11 studies; 2 FASTQ-only studies deferred): see
`PIPELINE_INSTRUCTIONS.md` Section 3/6.

## Phase 0 — Environment (2026-07-16)
- Built dedicated venv at `/ref/rmlab/software/azamat/als_pipeline_env` (Python 3.11),
  self-contained (not `--system-site-packages`), seeded only from another user's
  interpreter to create the venv.
- Installed: scanpy 1.11.5, anndata 0.12.19, mudata 0.3.10, muon 0.1.7, pandas 2.3.3,
  pyarrow 25.0.0, h5py 3.16.0, scipy 1.17.1, numpy 2.4.6. Frozen to
  `scripts/requirements.txt`.

## Phase 1 — Shared helper scripts (2026-07-16)
- `scripts/conversion_join_helpers.py`: verified per-study metadata join logic
  (standard GSM-regex join; Schweingruber `Cell_NNN`-via-title; Ho2021
  `{group_code}_{donor_id}[_{day}]`-via-title; pTDP43 RNA/ATAC pairing by
  filename group-replicate suffix). See project memory
  `project_als_pipeline_metadata_joins` for how each was derived/verified.
- `scripts/conversion_io_helpers.py`: recursive tar extraction, bulk
  Parquet+TSV writer.
- `scripts/conversion_log_writer.py`: writes each study's `processed/conversion_log.md`
  per Section 2's required fields (source file(s), target file, library+version,
  filtering applied, row/col counts before/after, date).

Bugs caught by code review + generated tests during Phase 1 (all fixed before
pushing to HTCF):
- `tarfile.extractall(..., filter="data")` would crash on Python interpreters
  without the PEP 706 backport (feature-detected via `inspect.signature` now,
  not a version-number guess). Verified: HTCF's pipeline venv (Python 3.11)
  does support it; local dev Python 3.9.6 doesn't.
- `.tgz` nested archives were extracted into a directory still named `*.tgz`
  (only `.tar` was being stripped) — fixed with a proper suffix-stripping helper.
- Several auto-generated unit tests for `recursive_extract` and
  `write_conversion_log` were themselves wrong (asserting on the wrong mock
  object in a mocked `Path`/`/`-operator chain, or assuming a different
  `Path(...)` call signature than the code actually uses) — replaced with real
  `tmp_path`-based integration tests instead of chasing brittle mocks.

## Metadata fixes applied back to samples.json / all_samples.tsv
(Populated as each study is converted — see per-study sections below for what
changed and why.)

## Phase 2 — Per-study conversions
(One subsection per study, added as each is completed.)

### NatureAging2024_ETneurons — DONE (2026-07-16)
- Source (`GSM7083181_MotorCortex_02202018.ICA_res0.1_mingenes400.raw.dge.txt.gz`)
  is NOT a dense plain-text DGE table as the pipeline doc's Section 3 describes —
  it's a non-standard sparse MatrixMarket-style file with gene names/cell barcodes
  embedded in `%%GENES`/`%%CELL_BARCODES` comment lines before the dims line.
  Custom parser written (`convert_NatureAging2024_ETneurons.py`).
- File header declared nnz=121,375,751; actual data lines parsed=~121,353,126
  (~0.02% diff) — built from actual parsed lines, noted in conversion_log.md.
- **Finding:** cell barcodes embed real per-cell structure GEO's single-GSM
  record doesn't capture — 8 pools across ALS/Control. Recovered as
  `obs["barcode_pool"]` / `obs["barcode_disease_group"]`, kept separate from
  GEO-sourced normalized columns (see `project_als_pipeline_metadata_joins` memory).
- **Bug caught in review + Slurm run, fixed before final success:** broadcasting
  a `None`-valued samples.json field (e.g. `cell_line_or_donor`) directly into
  `adata.obs` crashes h5ad writing (`Can't implicitly convert non-string objects
  to strings`). Fixed generally in `conversion_join_helpers.h5ad_safe_value` /
  `attach_metadata_per_cell` (None → "NA"), not just patched locally — every
  other study will hit the same issue for any null metadata field.
- Slurm job 43601613: 119,510 obs x 29,375 vars, converted + verified in 62s,
  32GB mem request (actual usage far lower). Output copied to
  `studies/NatureAging2024_ETneurons/processed/`, scratch cleaned up.

### Brain2025_Multiome + CrypticExon_ActaNeuropathol2023 — DONE (2026-07-16)
- Both already-h5ad CELLxGENE studies; shared logic in new
  `scripts/conversion_cellxgene_helpers.py` (join by matching each h5ad's cell
  count against `cellxgene_metadata.json`'s per-dataset `cell_count`, which
  uniquely identifies the `dataset_id` == samples.json `sample_id`; rename
  `donor_id/disease/tissue/assay` to the collection's normalized field names;
  broadcast study-level fields with no per-cell CELLxGENE counterpart).
- **Interpretation flagged:** each study has multiple anatomically-distinct
  h5ad files (Brain2025: brain vs spinal cord; CrypticExon: frontal/occipital
  cortex x 2 genotype groupings). Kept as separate output files rather than
  merged into one, per Section 1's "never merge... at this stage" — Section 7's
  single-file-per-study layout is a suggestion, not a hard rule, per its own wording.
- **Bug caught by code review, fixed before rerun:** `convert_cellxgene_study`
  duplicated the output-filename transform inline instead of calling the new
  `derive_output_name` helper, and a verify script had a hand-typed expected-filename
  list that silently drifted from what convert actually produced — CrypticExon's
  real filename `"...C9-ALS_ C9-ALS_FTD..."` has a pre-existing underscore next to
  a space, producing a double underscore after `.replace(" ", "_")` that the
  hand-typed list didn't account for, causing a false VERIFY:FAIL on an otherwise
  correct conversion. Fixed by having convert and verify both call the one
  `derive_output_name` function (verify now imports `RAW_FILENAMES` from its
  sibling convert script rather than hardcoding names at all).
- **Bug caught by manual inspection, fixed before final copy to /lts:**
  `adata.write_h5ad()` doesn't preserve compression by default — source
  CELLxGENE files use gzip, so the first (uncompressed) output was ~5x larger
  (Brain2025: 1.0GB raw -> 5.4GB uncompressed). Fixed by passing
  `compression="gzip"` explicitly in `convert_cellxgene_study`.
- Also caught (code review): `verify_cellxgene_outputs` only checked
  `BROADCAST_FIELDS`, never the 4 renamed per-cell columns
  (`cell_line_or_donor`/`disease_status`/`tissue_or_cell_type`/`platform`) — an
  output missing a rename (source column absent) would have verified as PASS.
  Fixed to check both sets of columns.
- Final Slurm runs (jobs 43602606, 43602607, both with compression fix):
  Brain2025_Multiome 2 outputs (75,583 + 62,711 obs), CrypticExon 4 outputs
  (66,719 / 160,658 / 113,106 / 120,807 obs), all sizes now match source (e.g.
  Brain: 1.03GB vs 1.03GB raw, vs the earlier 5.4GB uncompressed mistake).
  Both copied to their `processed/` dirs, scratch cleaned up.

### Qki5_PNAS2024 — DONE (2026-07-16)
- 3 data products: GSE267791 (scRNA, 10x triplet) -> h5ad; GSE218824 (hiPSC-MNs
  bulk) + GSE218820 (OPC bulk) -> Parquet+TSV each; both bulk series' AS-events
  tarballs -> `processed/qki5_as_events/<GSM>/` as-is.
- **Finding:** GSE267791's 4 GSM records are metadata-identical placeholders
  (only `sample_id` differs — verified all other normalized fields match
  exactly across all 4). Combined with barcode suffixes uniformly `-1` (not
  the CellRanger `aggr` per-sample convention), there is no way to split cells
  by sample. `sample_id` is stored as all 4 GSMs semicolon-joined rather than
  arbitrarily picking one; a defensive assertion raises if any other field
  ever diverges across the 4 records.
- **Finding:** the bulk RPKM files (`*.expr.txt.gz`) have no raw-count column
  at all — only RPKM. Noted in conversion_log since this differs from other
  studies' bulk tables (e.g. DivergentC9 uses counts as primary), so
  cross-study comparisons of this table need re-normalization awareness.
- **Bug caught by generated tests, fixed before Slurm run:** hardcoded
  `tf.extractall(..., filter="data")` directly in the new script instead of
  reusing the version-safety wrapper already built for exactly this problem —
  refactored that wrapper out of `recursive_extract` into a new
  `conversion_io_helpers.safe_extractall()` so both call sites share it, then
  actually called it here (the import was already there, unused).
- **Bug caught by first Slurm run:** forgot to push the updated
  `conversion_io_helpers.py` (containing `safe_extractall`) to HTCF after
  adding it — job failed instantly on `ImportError`. Fixed by pushing and
  resubmitting.
- Also caught (code review) in the verify script: scRNA `.obs` was never
  checked against the required metadata columns, and unguarded
  `obs["sample_id"]` access would crash instead of a clean VERIFY:FAIL on a
  malformed object.
- Also caught: an auto-generated test file for the verify script did
  `sys.modules['anndata'] = MagicMock()` at import time with no teardown,
  which — because sys.modules is process-global — silently broke unrelated,
  already-passing tests in the sibling convert-script test file when both
  ran in the same pytest session. Rewrote using real tmp_path fixtures and
  scoped `monkeypatch` instead, eliminating the whole class of bug.

### Zelic2025_Immunity — DONE (2026-07-16)
- 4 data products, kept as 4 separate outputs (never merged): GSE287439
  (human, iPSC tri-culture necroptosis model, 10 GSMs) -> h5ad; GSE287257
  (human, ALS/control spinal cord snRNA, 12 GSMs) -> h5ad; GSE287569 -> h5ad;
  GSE287256 (bulk RNA-seq, 12 samples) -> Parquet+TSV.
- **Finding requiring a species check:** GSE287569 ("SOD1") is confirmed
  **Mus musculus**, not human like the other two scRNA series (verified via
  samples.json organism field) — a hard reason these 3 series can never be
  combined into one object, beyond just "different designs."
- **Finding — unresolvable metadata gap, flagged rather than guessed:** the
  bulk RNA-seq CSV's column headers (`165_S165`, `166_S166`, ...) do not
  match any GSM title, donor ID, or other field in samples.json,
  series_metadata.json, OR the live GEO record for this series (checked via
  direct GEO lookup, 2026-07-16) — no published crosswalk exists between
  these internal sequencing sample IDs and the 12 GSM accessions. Per-sample
  fields that would require this crosswalk (genotype, disease_status,
  cell_line_or_donor, treatment, sex, timepoint_or_age, batch) are set to the
  literal string `"UNRESOLVED_GSM_MAPPING"` rather than guessed via column
  order or silently omitted. Fields verified identical across all 12 GSM
  records (organism, tissue, assay_type, source_doi_or_pmid, etc.) are still
  attached normally, with a defensive assertion that raises if that
  identical-across-all-records assumption is ever violated.
- Standard per-cell join for the 3 scRNA series: each GSM's 10x h5 is read,
  cells prefixed with `{GSM}_{barcode}` to avoid collisions, then all GSMs
  within a series concatenated (inner join on genes) into one object per series.
- **Bug caught by manual inspection of Slurm stderr** (harmless warning, but a
  real data-quality issue): `ad.concat()` across per-GSM objects reintroduced
  duplicate `var_names` even though each GSM had already been through
  `var_names_make_unique()` individually. Fixed by calling
  `combined.var_names_make_unique()` again post-concat — same fix applied
  proactively to HammellOneill2025_CellReports before its first run, since it
  concats per-GSM objects too. Zelic2025 was rerun with the fix (6:43,
  verified clean — no more duplicate-var warnings).
- Final: 3 scRNA h5ad (46,487 / 114,161 / 15,854 obs) + 1 bulk table (12 x
  18,150), all copied to `processed/`.

### HammellOneill2025_CellReports — DONE (2026-07-16)
- 6 GSMs, each a nested `*_count_matrix.tar.gz` inside `GSE271156_RAW.tar` —
  exactly the case `recursive_extract` was built for. Standard 10x mtx triplet
  per GSM (no special naming), concatenated (inner join, `var_names_make_unique`
  applied post-concat per the fix above) into one h5ad: 26,704 obs x 37,786 vars,
  6 samples verified. Copied to `processed/`.

### Lall2025_CellStemCell — BLOCKED, SKIPPED for now (2026-07-16)
Two independent, unresolved complications found; user chose "investigate
further" for the first, then gave standing guidance to skip blocked studies
and move on rather than pausing on each one.

1. **snRNA-seq (GSE255605, 17 GSMs) gene identity is unrecoverable.** Each
   `*_filtered_genesummed_mtx.csv.gz` has cell barcodes as the header but NO
   gene identifier column at all — 36,591 data rows with gene identity
   implied entirely by row position against an unstated reference.
   - Confirmed via GEO's own per-GSM "Data processing" text (fetched
     2026-07-16): CellRanger v6.1.2, `--include-introns`, reference **v2020-A**
     (GRCh38-2020-A), with Ensembl IDs then "summed to gene symbol level."
   - Found the exact reference package already on HTCF:
     `/ref/gzlab/software/cellranger/refdata-gex-GRCh38-2020-A` (another lab's
     shared resource, read-only use). Its GTF has exactly 36,601 unique
     `gene_id`s and 36,591 unique `gene_name`s — an EXACT match to the data's
     row count, confirming the right reference build (not a guess).
   - The remaining unknown is row ORDER. Tested two hypotheses against real
     expression data (checking MALAT1/GAPDH/ACTB, which should show
     near-ubiquitous high expression in any real snRNA sample):
     - Alphabetical sort of gene symbols: MALAT1's candidate row was 100%
       zero across 6,728 cells — impossible for real data, hypothesis rejected.
     - Genomic/first-occurrence order (matching CellRanger's own
       `features.tsv` convention): MALAT1 candidate showed only 18% detection
       (implausibly low), ACTB candidate came back 100% zero. Also rejected.
   - Neither hypothesis holds; the true order depends on unpublished analysis
     code (an R `rowsum`/`aggregate` call whose exact behavior isn't
     documented). Not resolvable without contacting the authors or finding
     their code. Left unconverted rather than fabricate gene identities.
2. **Bulk RNA-seq (GSE255602, 71 samples) column-to-GSM crosswalk is messy
   and not yet verified.** Column names like `M1-3_EDi022-A_CTR_06` combine:
   an experiment-batch token (title's "experiment 1.3" -> "M1-3", dot to
   hyphen), the donor/cell-line code (direct match, but titles have
   inconsistent whitespace: "line 3CA9iALS" vs "line3CA9iALS"), a
   conditional genotype suffix (`_CTR` appended only for control lines --
   ALS lines already embed genotype in the cell-line name itself, e.g.
   `9FP9iALS`), and a zero-padded rep number or literal `96` for "96 Well"
   samples. Plausible but not yet exhaustively verified against all 71
   columns/records the way DivergentC9's crosswalk was — deferred rather
   than risk a subtly wrong mapping.
- **Not attempted at all:** the 2 files are simply left unconverted; nothing
  was written to `processed/` for this study. Revisit with the user before
  proceeding.

### DivergentC9_NatComms2023 — first run caught a real data gap (2026-07-16)
- First Slurm run (job 43602804, ran 1h32m) succeeded end-to-end but
  **verify correctly failed**: "expected 34 snRNA samples, found 33." Root
  cause was a real bug, not bad luck: `GSM6781920` (C9FTD donor F2,
  FrontalCortex) has only the raw pre-correction 10x triplet in the deposited
  data — no `cellBender_corrected_filtered.h5` at all, unlike the other 33
  GSMs. The original `convert_snrna` only iterated over cellBender files
  found via glob, so it silently dropped this GSM's entire ~cells worth of
  data with zero indication anything was missing — verify happened to catch
  it only because it separately checked the sample count against samples.json.
- Fixed to explicitly iterate over all 34 expected GSMs (from samples.json,
  not from glob results), and for any GSM lacking a cellBender file, include
  it using the raw triplet as BOTH the primary matrix (X) AND
  `layers["raw_precorrection"]` (the raw triplet genuinely IS all that
  exists for it, not a stand-in) — clearly flagged in
  `adata.uns["processing_notes"]` rather than silently dropped. Added a
  regression test for this exact scenario.
- Resubmitted (job 43607345) with the fix.

### DivergentC9_NatComms2023 — second run found a WORSE bug in the fix itself (2026-07-17)
- Job 43607345 completed and verify PASSED, but manual inspection caught
  `6,998,362 obs` where ~200K was expected. Root cause: the fix above used
  `GSM6781920`'s raw 10x triplet as the PRIMARY matrix directly — but a raw
  (pre-cell-calling) 10x triplet contains the ENTIRE barcode whitelist
  (~6.8-6.9M barcodes, almost all empty droplets), not real cells. That
  single GSM's raw triplet dumped millions of non-cell barcodes into the
  main harmonized object. verify didn't catch it because it only checked
  sample count, not obs magnitude — a real gap, now fixed (see below).
- Real fix: `GSM6781920` (or any GSM lacking a cellBender file) is now
  EXCLUDED from the main 33-sample harmonized object and written to its own
  separate `DivergentC9_NatComms2023_snRNA_GSM6781920_unfiltered_no_cellcalling.h5ad`
  instead — not silently dropped (the original bug), not merged in unfiltered
  (the second bug), but explicitly excluded-and-documented, with the
  companion file available for whoever wants to apply their own cell-calling.
  `verify_DivergentC9_NatComms2023.py` updated: expects exactly 33 (not 34)
  main-object samples, checks the companion file exists, checks
  `GSM6781920` is NOT in the main object, and added an obs-count sanity
  range (50K-500K) specifically to catch this class of bug in the future.
  Rewrote the regression test accordingly. Resubmitted as job 43619067.

### Lall2025_CellStemCell — flag file added to its own directory (2026-07-17)
- Per user request ("can we just flag this study? maybe in its associated
  data file?"), wrote `CONVERSION_BLOCKED.md` directly into
  `studies/Lall2025_CellStemCell/processed/` (empty otherwise), summarizing
  both open blockers (unrecoverable snRNA gene row order; unverified bulk
  crosswalk) so anyone browsing that study's own folder sees the blocker
  without needing to read this doc or the coordination status files.

### Cross-cutting bug: `normalized()` strips `title`/`gsm`, breaking title-based joins (2026-07-17)
- Discovered when Schweingruber's and Ho2021's first Slurm runs (jobs
  43618839, 43618840) BOTH failed immediately: `build_schweingruber_cellid_index`
  and `build_ho2021_donor_index` need each GSM record's `title` field, but
  `samples.json`'s `normalized` sub-object never includes `title` (only the
  raw top-level record does) — `normalized(load_samples(...))` silently
  strips it, so every record hit the join function with `title=None`.
  `pair_ptdp43_samples` has the same issue with `gsm` (normalized records
  have `sample_id` instead, same value, different key name).
  Local unit tests for both studies had passed despite this, because the
  test fixtures happened to include `title`/`gsm` directly on an
  otherwise-normalized-shaped dict — the fixtures didn't accurately mirror
  what `normalized()` actually produces in production. A real gap in my own
  testing, not an auto-generated-test problem this time.
- Fixed generally: added `normalized_with_title()` to
  `conversion_join_helpers.py` (normalizes AND re-attaches `title`+`gsm` from
  the raw record). `convert_Schweingruber2025_NatComms.py`,
  `convert_Ho2021_CellSystems.py`, and `convert_pTDP43_PNAS2025.py` (not yet
  submitted at the time, fixed proactively) now call this instead of plain
  `normalized()`. Existing shared helper test suite
  (`scripts/tests/test_conversion_join_helpers.py`, 64 tests, pre-existing)
  still passes unchanged.

### Schweingruber2025_NatComms — DONE (2026-07-17)
- `GSE226482_counts.txt.gz` (primary, `layers["raw"]`) + `_rpkms.txt.gz`
  (`layers["rpkm"]`), R-style whitespace-delimited tables (header has one
  fewer field than each data row — the gene-symbol row-name column has no
  header entry), joined to samples.json via the `Cell_NNN` suffix in each
  GSM's `title` (see `project_als_pipeline_metadata_joins` memory).
- Job 43619952 (resubmit after the `normalized_with_title` fix) running.

### Ho2021_CellSystems — DONE (2026-07-17)
- 7 physical batch CSVs (Batch A, B1, B2, C, D, E, F — Batch B split across
  2 files) joined per-column via the `{group_code}_{donor_id}[_d{day}]`
  token embedded in each cell-barcode column name, matched against the GSM
  `title` WITHIN the same experimental batch — verified 2026-07-17 that
  donor+day combinations repeat as DIFFERENT GSMs across different batches
  (e.g. `C9O_0029_d18` exists in both Batch D and Batch E), so batch-scoping
  the join is required, not optional. `adata.obs["batch_platform"]`
  distinguishes ddSEQ (Batches A-D) from 10x (Batches E-F).
  `ad.concat(join="inner")` across all 7 files, `var_names_make_unique()`.
- Job 43619953 (resubmit after the `normalized_with_title` fix) running.

### pTDP43_PNAS2025 — RNA modality DONE, ATAC/h5mu blocked (2026-07-17)
- RNA: 26 per-GSM 10x CellRanger `filtered_feature_bc_matrix.h5` files
  (extracted from the 51.5GB `GSE212630_RAW.tar` via a single full
  `extractall` pass, not a `getmembers()`-filtered one — per
  PIPELINE_INSTRUCTIONS.md Section 5, listing/indexing this specific tar is
  slow enough to time out, and `getmembers()` would hit the same full-tar
  scan). Each RNA GSM's paired ATAC GSM (by `{group}-{replicate}` filename
  suffix — the two modalities do NOT share a GSM, verified 2026-07-16) is
  preserved as `adata.obs["atac_gsm"]`.
- ATAC / combined `.h5mu`: NOT built. All 26 ATAC GSMs provide ONLY raw
  fragment files (`*_atac_fragments.tsv.gz` + `.tbi.gz`), no peak-called
  count matrix — building one needs real peak-calling (e.g. MACS2) or a
  fixed-genome-bin matrix, a separate analysis step beyond this pipeline's
  format-conversion scope. Flagged via `PTDP43_ATAC_BLOCKED.md` written to
  `studies/pTDP43_PNAS2025/processed/` (3 options laid out: proper peak
  calling, fixed-bin matrix, or skip ATAC entirely for now) rather than
  guessing at parameters or blocking the RNA deliverable on it.
- Job 43619954 (first submission) running — large tar extraction, budgeted
  `--mem=64G --time=04:00:00`.

### Multi-session coordination protocol adopted (2026-07-17)
- A 4th, orchestrating session set up
  `/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/` (separate from
  the dataset collection root) with `PROTOCOL.md`, `CHANGELOG.jsonl`, one
  status JSON per role (`download_metadata`, `conversion`, `verification`),
  per-role checkpoints, and advisory locks. This session's role is
  `conversion`. Per the ownership table, `CATALOG.md` is now owned by
  `download_metadata` — this session no longer edits it directly (previously
  did); conversion-side updates go in this doc plus `conversion_status.json`
  and `CHANGELOG.jsonl` instead, for the owner to pick up.

### Ambient RNA correction (DecontX) — planning notes (added 2026-07-27)

An external collaborator running their own `commons` pipeline against our
converted `.h5ad` files (found on HTCF at
`/scratch/sahlab/shandley/ndc_code/commons/`, a different lab's scratch space
— read-only reference, not ours) found a classic ambient-RNA contamination
pattern in `Brain2025_Multiome` and `CrypticExon_ActaNeuropathol2023`:
pan-neuronal markers (STMN2, SNAP25, NEFL, NRGN) reading as spuriously up in
glial cell types in ALS samples. Investigating their tooling's actual source
(`h5ad_read.py`) surfaced a separate, useful fact: their `pick_counts()`
function auto-selects a count matrix by checking `adata.layers['counts']`
first, then AnnData's dedicated `.raw` slot, then falling back to `X` — it
never looks for `layers['raw']`, which is this pipeline's own established
name for the pre-pipeline-filtering counts layer (see `PIPELINE_INSTRUCTIONS.md`
Section 2a). This is a pre-existing naming mismatch between our schema and
their auto-detection, not something DecontX introduces — flagged here for
visibility, not fixed; renaming an established convention is the user's call,
not something to do silently as a side effect of this DecontX work.

**Why DecontX over CellBender/SoupX:** those tools need the true unfiltered,
empty-droplet-inclusive barcode matrix to estimate ambient background — an
audit (`AMBIENT_RNA_RAW_DATA_AUDIT.md`, coordination root, produced by
`download_metadata`) confirmed only `DivergentC9_NatComms2023`'s snRNA arm
actually has that data downloaded; getting it for the rest would mean
contacting authors or downloading and CellRanger-processing raw FASTQ, both
expensive. DecontX (Bioconductor's `celda` package) was chosen specifically
because its `background` (raw-matrix) parameter is optional per its own
documentation — its core Bayesian model estimates per-cell contamination
using only the filtered matrix, via cross-cluster consensus profiles. Full
scope, schema (`layers["decontx_corrected"]`, `obs["decontx_contamination"]`),
and per-study instructions are in `PIPELINE_INSTRUCTIONS.md` Sections 2a/2b/8
(the last covering which already-converted studies need a full re-run).

### DecontX — R environment setup and pilot re-run (2026-07-28)

- Built a dedicated R environment at `/ref/rmlab/software/azamat/als_pipeline_r_libs`,
  reusing the `sqanti3_env` conda R 4.5.3 interpreter (avoids a from-scratch R
  build) but installing into this new library path EXCLUSIVELY (not layered on
  top of `sqanti3_env`'s own library), so nothing here can affect SQANTI3's
  package versions and vice versa. `celda` 1.26.0 installed via
  `BiocManager::install`.
- **Install-time issues found and fixed** (`scripts/decontx/install_decontx_env.R`
  + `.sbatch`):
  1. `sqanti3_env`'s bundled compiler wrappers (`x86_64-conda-linux-gnu-cc`/`c++`)
     aren't found unless the env's `bin/` is on `PATH` -- without it every
     package with native code failed with "command not found".
  2. The R package `Cairo` (a hard `Import` of `celda`'s `Import` `scater`, via
     `ggrastr` -- not optional/skippable) needs a system `cairo.h`, which
     doesn't exist anywhere in this conda env. Resolved by pointing
     `PKG_CONFIG_PATH` at a spack-built `cairo` already on HTCF
     (`/ref/rmlab/software/spack/...`), plus its full transitive pkg-config
     dependency chain identified from `libcairo.so`'s own RPATH for guaranteed
     version compatibility: `pixman`, `libpng`, `glib-2.0` -> `libpcre`,
     `libffi`. Verified by hand with `pkg-config --cflags cairo` (non-empty
     `-I` flags) before resubmitting, rather than guessing and re-queueing.
  3. Wrote the acceptance test as an actual `decontX()` call on synthetic data
     (not just `requireNamespace()` checks) -- caught a real mistake this way:
     `decontX()`'s return value differs by input type. For a
     `SingleCellExperiment` input it returns an SCE (accessed via
     `decontXcounts()`/`colData()$decontX_contamination`), but for a
     plain-matrix input (this pipeline's approach -- see below) it returns a
     **plain list** with `$decontXcounts`/`$contamination` directly. Confirmed
     against celda's own `?decontX` docs after the SCE-style accessors failed
     with "unable to find an inherited method ... signature 'object = list'".
     Both `install_decontx_env.R`'s smoke test and the production
     `run_decontx.R` were using the wrong accessor form initially; fixed in both.
  4. Also note: package installation must run via `srun`/`sbatch` on a compute
     node, never directly on the login node -- the login node has an older
     glibc than compute nodes here, so a compiled package's `.so` (e.g. `uwot`)
     that loads fine on a compute node can fail with a `GLIBC_2.29 not found`
     error on the login node. Any ad-hoc R check needs `srun`, not a bare
     `ssh ... Rscript`.
- **R<->Python bridge**: no zellkonverter/anndata2ri/basilisk dependency --
  `scripts/decontx/decontx_io.py` exports `X` (and, for
  `DivergentC9_NatComms2023` only, `layers["raw_precorrection"]` as
  `background`) to a plain 10x-style mtx/barcodes/features triplet;
  `scripts/decontx/run_decontx.R` reads it, runs `decontX()`, writes
  `decontx_counts.mtx` + `contamination.tsv` + `barcodes.tsv`/`features.tsv`
  back out; `decontx_io.import_decontx_results` reimports and attaches to the
  AnnData object. Cell AND gene order are both explicitly re-verified against
  `adata.obs_names`/`var_names` on reimport (raises rather than assumes) --
  the same defensive-assertion pattern as `DivergentC9`'s obs-count sanity
  check. `scripts/decontx/apply_decontx.py` is the driver (export -> Rscript
  subprocess -> reimport -> write a fresh h5ad to a temp path, rename into
  place only on success); `scripts/decontx/decontx_verify_helpers.py` has the
  shared structural checks (shape, no-NaN/range on contamination, X and
  `layers["raw"]` untouched, a same-first-500-cells no-op detector) plus the
  actual biological acceptance check from Section 2b (marker-gene reduction in
  glial cell types), reserved for `Brain2025_Multiome`/`CrypticExon_ActaNeuropathol2023`
  where the ambient-RNA pattern was originally found.
- **Pilot re-run: `HammellOneill2025_CellReports`** (chosen as the smallest
  non-CELLxGENE droplet study, no native cell-type column so DecontX used its
  own internal auto-clustering, no background matrix available per
  `AMBIENT_RNA_RAW_DATA_AUDIT.md`). Slurm job 44076834: converged after 147
  iterations (~5 min), contamination range [0.0003, 0.9996] mean 0.1625.
  Verified structurally against both the scratch output and, separately, the
  final `/lts` copy post-handoff (all pre-existing obs columns and
  `layers["raw"]` unchanged, shape matches, `layers["decontx_corrected"]` +
  `obs["decontx_contamination"]` present and sane). Copied scratch -> `/lts`
  from the login node per Section 5's convention. This confirms the mtx
  export/reimport bridge and the R environment work end-to-end on real
  production data before rolling out to the remaining 8 studies in Section 8's
  list (`Ho2021_CellSystems`, `Zelic2025_Immunity` x3 series,
  `NatureAging2024_ETneurons`, `Qki5_PNAS2024` scRNA-only, `Brain2025_Multiome`,
  `CrypticExon_ActaNeuropathol2023` x4, `pTDP43_PNAS2025` RNA-only,
  `DivergentC9_NatComms2023`). Note: `pTDP43_PNAS2025`'s re-run should wait
  for `download_metadata` to add the flagged `pTDP43_group` field (see
  `PAPER_METADATA_CROSSCHECK.md`/changelog 2026-07-27T21:30) so that fix lands
  in the same re-run rather than needing a second one.
