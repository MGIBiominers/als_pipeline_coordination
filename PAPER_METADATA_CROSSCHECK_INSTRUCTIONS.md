# Paper metadata cross-check — instructions for the verification role

**Added:** 2026-07-27, at the user's request, following a gap identified in
`METADATA_QC_FLAGS.md`'s own documented scope: existing metadata verification
cross-checks record *counts* and top-level *accession* fields against live GEO/
CELLxGENE, but never checks whether individual per-sample field *values*
(donor, genotype, disease status, tissue/cell type, sex, age, etc.) are
actually correct against the one source that would know — the paper's own
supplementary materials. A GEO characteristics field or a heuristic join
(regex/title-suffix matching — several studies in this collection use exactly
that, see below) can be internally consistent and completely wrong for a
specific sample, and nothing currently in place would ever catch that.

This is a genuinely different kind of check from anything verification has
done so far: it requires fetching each paper's own supplementary materials
and manually reconciling specific values, not querying a clean API like GEO's
`esummary`. Budget for it accordingly — this does not scale the way the
GEO-count check does.

## 1. Storage: `studies/<id>/literature/`

New per-study directory, alongside the existing `raw/` (download_metadata) and
`processed/` (conversion) — **owned by verification**, same pattern. Store:
- The paper's PDF (or full-text XML if fetched from PMC), if legitimately
  accessible (see acquisition rules below).
- Supplementary tables/files as deposited (Excel, CSV, PDF supplementary
  document) — whatever format the journal provides, unmodified.
- A short `literature/NOTES.md` per study recording: where each file came from
  (PMC / journal site / inaccessible), and which specific table/section was
  used for the cross-check.

Add this to `PROTOCOL.md`'s ownership table (`studies/<id>/literature/*` →
verification, others read-only) next time you touch that file, or ask the
orchestrating session to add it.

## 2. Acquisition — legitimate open-access routes only

**Do not** attempt to bypass paywalls, use shadow/pirate libraries, or scrape
authenticated content. Try, in order, and stop at the first that works:

1. **PMC (PubMed Central)**, via the PMID already recorded in each study's
   `samples.json`/`all_samples.tsv` (`source_doi_or_pmid` field). Most of this
   collection's papers are NIH/NINDS-adjacent ALS research and commonly have a
   PMC deposit (open immediately, or after a short embargo) — check via
   `efetch`/`elink` against PMC first. PMC deposits usually include
   supplementary files as separate downloadable items.
2. **The journal's own supplementary-materials page**, via the DOI. Many
   journals (including several in this collection — Cell Reports, Cell
   Genomics, Nature Communications, PNAS) host supplementary materials openly
   even when the main-text PDF sits behind a paywall — check for this
   specifically before concluding a paper is inaccessible.
3. **bioRxiv preprint** (if one exists for the paper) as a fallback for
   methods/sample-description text — note clearly that a preprint's
   supplementary tables may differ from the final published version if used
   this way; prefer the published version whenever accessible.

If none of these yield the supplementary materials, mark that study's
cross-check as `source_inaccessible` in `verification_status.json` and move
on. That is a legitimate, expected outcome for some studies — not a failure to
push through, and not a reason to attempt an access route outside the three
above.

## 3. What to actually cross-check

For each sample already in that study's `samples.json`/`all_samples.tsv`,
compare the normalized field values (`cell_line_or_donor`, `genotype`,
`disease_status`, `tissue_or_cell_type`, `sex`, `timepoint_or_age`, `batch`,
etc.) against whatever sample/donor-level table the paper itself provides
(commonly a "Supplementary Table 1"-style donor manifest, sometimes embedded
in the methods section instead of a separate table). Record, per sample or
per study (whichever the paper's own table's granularity supports):

- **MATCH** — paper's table agrees with what's already recorded.
- **MISMATCH** — paper's table disagrees; record both values and which one
  is correct once you've confirmed it (don't just flag a discrepancy without
  determining which side is right, where determinable).
- **NO_CROSSWALK** — the paper doesn't provide enough information to associate
  its own sample identifiers with GEO's GSM accessions at all (this is a
  distinct, honest outcome — same spirit as the existing
  `UNRESOLVED_GSM_MAPPING` marker already used for Zelic2025's bulk table).

## 4. Where the highest-value risk actually is — for your own prioritization

You decide ordering and pace (per the user's explicit instruction — this is
not a mandated sequence), but for context, here's what's already known to
carry the most risk of a value-level error slipping through undetected,
because these studies' metadata was assembled via heuristic joins rather than
a direct GSM-keyed lookup (see `project_als_pipeline_metadata_joins` and
`conversion_process.md` for the full derivation of each):

- **Ho2021_CellSystems** — donor/group/day recovered via a *batch-scoped
  title-suffix regex* match between raw CSV column headers and GEO `title`
  fields. A single mismatched regex capture would mislabel one sample without
  changing the overall count.
- **Schweingruber2025_NatComms** — 1,415 samples joined purely on a `Cell_NNN`
  suffix extracted from GEO's `title` field; the combined matrix has no other
  per-sample identifying information at all.
- **pTDP43_PNAS2025** — RNA and ATAC modalities paired by matching a
  `{group}-{replicate}` string in filenames (the two modalities don't share a
  GSM); a pairing bug would silently swap two samples' ATAC data without
  affecting any count.
- **DivergentC9_NatComms2023** — already has one confirmed real bug in this
  study (the GSM6781920 empty-droplet issue) — worth extra scrutiny on its
  other 33 GSMs' donor/genotype assignments too, given the demonstrated risk
  in this specific dataset.
- **Zelic2025_Immunity** (bulk table) and **Lall2025_CellStemCell** (bulk
  table) — both already have an *acknowledged, unresolved* crosswalk gap
  (`UNRESOLVED_GSM_MAPPING` for Zelic; "plausible but not exhaustively
  verified" for Lall's 71 columns). These are prime candidates for the paper's
  own supplementary table to actually resolve, if GEO's own metadata can't.

Every other study in the collection was assembled via a direct GSM-keyed join
(the generic `GSM\d+` regex on filenames) and is comparatively lower-risk for
this specific failure mode — but still worth reaching eventually, since a
paper cross-check is the only way to catch a GEO characteristics field itself
being wrong (not just the join logic), which is a possibility even for the
direct-join studies.

## 5. Output — and how the OTHER roles find out what needs correcting

- New file: `PAPER_METADATA_CROSSCHECK.md` at **the coordination root**
  (`/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/` — NOT the
  `EXTERNAL_DATASETS` dataset collection; everything agent-facing consolidated
  there 2026-07-27, see `PROTOCOL.md`'s root descriptions if this is
  surprising). Same narrative-plus-flags convention as `METADATA_QC_FLAGS.md`
  (also at the coordination root) — you own both.
- Per-study, add a `paper_crosscheck` field to each study's entry in
  `verification_status.json` (coordination root): one of `not_started` /
  `in_progress` / `matches` / `mismatch_found` / `no_crosswalk` /
  `source_inaccessible`, with a `note` explaining findings — this is separate
  from the existing `phase` field (which tracks structural h5ad verification),
  since a study can be structurally `verified` while its paper cross-check is
  still `not_started`.
- **For any confirmed `MISMATCH`, don't just log it — file it as an
  actionable correction request**, the same way `verification` already does
  for other findings that need another role's action (see the
  `DivergentC9_NatComms2023` `verify_failed` precedent, which `conversion`
  picked up and fixed):
  1. Append a `CHANGELOG.jsonl` entry with `action: "flag_for_owner"`
     specifically (not a generic note — this is the verb the other roles
     already watch for), `study_id` set, and a `note` giving the exact field,
     the wrong value currently in `samples.json`/`all_samples.tsv`, the
     correct value per the paper, and which table/page you confirmed it from.
  2. `samples.json`/`all_samples.tsv`/`studies.tsv` are owned by
     `download_metadata` — that's who needs to apply the correction, not you
     (per the ownership table, you flag, the owner edits).
  3. **If that study has already been converted** (check
     `conversion_status.json` for its phase), say so explicitly in the same
     changelog entry — `conversion` needs to re-run it once
     `download_metadata` corrects the source metadata, the same "already-done
     work needs a re-run" pattern used for the DecontX rollout in
     `PIPELINE_INSTRUCTIONS.md` Section 8. A structurally `verified` study's
     h5ad still has the OLD wrong value baked into its `.obs` until that
     re-run happens — don't assume the fix propagates on its own.
