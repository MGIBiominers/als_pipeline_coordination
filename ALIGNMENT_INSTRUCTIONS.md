# ALS Dataset Collection — FASTQ Alignment Pipeline

> **Multi-session coordination:** this collection is shared with concurrent
> download/metadata, conversion, and verification sessions. Before starting
> work, read `/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/PROTOCOL.md`
> and check `/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/CHANGELOG.jsonl`
> since your last checkpoint (`checkpoints/alignment.txt`). Update
> `alignment_status.json` (your own file) as you go.

**Target audience:** Claude Code, turning FASTQ-only studies into standard
count matrices that the `conversion` role can consume unchanged.
**Collection root:** `/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS`
**Compute:** HTCF Slurm cluster. Same `/lts` read-only-on-compute-nodes
constraint as `PIPELINE_INSTRUCTIONS.md` — read raw FASTQ from `/lts`, write
all alignment output to scratch, verify, then copy back via a login-node
command.

## 1. Goal and handoff boundary

Take a study from `download_metadata` once its FASTQ set is fully downloaded,
and produce standard 10x-format count matrices in the *same* file format
`conversion` already knows how to read (`filtered_feature_bc_matrix.h5`,
`raw_feature_bc_matrix.h5`) — so `conversion` needs zero new code, just a new
per-study entry in `PIPELINE_INSTRUCTIONS.md` Section 3 once a study lands
here. This role does alignment/counting only — it does not touch metadata
normalization (`download_metadata`'s job) or format conversion to `.h5ad`
(`conversion`'s job).

**Execution mechanism, added 2026-08-24 — read before writing a single
sbatch script by hand:** the CellRanger RNA track (`OFC_APA_CellGenomics2025`'s
RNA arm + `Pineda2024_Cell`) is now a real, validated Nextflow pipeline at
`EXTERNAL_DATASETS/scripts/alignment/nextflow_cellranger/`, not a per-sample
hand-written script. **Use it — do not hand-roll a new sbatch script for
CellRanger work Sections 5-6 below describe; that manual approach is what
this pipeline replaced.** Section 6a covers how to actually run it. Sections
2, 3, 5 below are still the real domain knowledge the pipeline's samplesheet
encodes (chemistry, per-study routing, the mixed-species gotcha) — read them,
just don't re-implement them as a new sbatch script.

Current real state (updated 2026-08-27): the pipeline is live in production,
running real CellRanger compute, not just stub-validated. First real test (3
samples: SRR27882086/091/094) completed cleanly and synced to `/lts`
2026-08-25 — healthy cell counts, correct GRCh38-2024-A routing, sync
verified 3/3. The full remaining `Pineda2024_Cell` human batch (146 samples,
driver job 45795966) has been running since 2026-08-25T01:00 (multi-day —
this is expected and fine, not a hang; see Section 6a's `-resume` note if it
ever needs resubmitting). Two real bugs were found and fixed in this batch
before they could corrupt output (a FASTQ-length-heuristic gap affecting 43%
of remaining runs, and a Groovy string-escaping bug) — see `CHANGELOG.jsonl`
2026-08-25 entries for the full diagnosis if either resurfaces.
**Known, already-diagnosed issue (2026-08-27, do not re-diagnose from
scratch):** a small number of samples (~2% so far: SRR27882080/157/213) are
genuine deep-sequencing outliers (4-5x the compressed FASTQ size of a normal
sample) that exhaust `CELLRANGER_COUNT`'s fixed 8h time limit on every retry
attempt, even though memory escalates (96→128→160GB) per attempt, because
only memory — not time — escalates with `task.attempt`. This is a deliberate
design tradeoff, not an oversight: raising the shared 8h default for every
sample in every future study was judged not justified by a ~2% outlier rate
with no more evidence yet. **Handling**: let the pipeline's automatic retries
exhaust naturally (does not block other samples), then rerun any that
permanently fail by hand with an explicit longer time budget (e.g. 16-20h),
rather than editing `cellranger_count.nf`'s shared `time` directive. Revisit
the shared default only if the outlier rate turns out to be materially higher
than ~2% once the full batch finishes.

The long-read track (Section 9, `SRP566214_dataset`) and the contingent bulk
STAR track (Section 10) are separate, not yet built as Nextflow pipelines —
this doesn't apply to them.

**In scope now:** `OFC_APA_CellGenomics2025`, `Pineda2024_Cell` (both 10x/
CellRanger, Sections 2-7 below), and, added 2026-08-19 by explicit user
request, `SRP566214_dataset` — ONT long-read bulk-style RNA-seq, fundamentally
different tooling (no droplets, no CellRanger concept applies). See the
dedicated **Section 9** for this study — do not try to fit it into Sections
2-7's CellRanger-specific steps.

**Contingent capability, no study needs it yet:** Section 10, added
2026-08-21, specifies a short-read bulk RNA-seq (STAR) alignment track for
*if* a FASTQ-only bulk study is ever added to this collection — every bulk
study currently in the collection already has a processed count matrix
deposited by its original authors (see `PIPELINE_INSTRUCTIONS.md` Section 9),
so there is no live work under Section 10 today. Don't start anything there
without first confirming a real FASTQ-only bulk study actually exists.

## 2. Step 0 — confirm actual per-study status before touching anything

**Both studies' Step 0 items below are now resolved** (`Pineda2024_Cell` since
2026-07-27, `OFC_APA_CellGenomics2025` since 2026-08-26) — kept here as a
worked example of the "verify the file count yourself, don't trust the
status file blindly" principle, and as the template to follow for any future
study added to this pipeline's scope. **Do not submit a real alignment job
for a study until its own Step 0 item is resolved** — check
`download_status.json` and `CHANGELOG.jsonl` for whether `download_metadata`
has closed a future study's version of this out:

- **`Pineda2024_Cell`**: confirmed via direct file count (2026-07-27) that all
  152 unique SRA runs are present with exactly 2 files each (R1+R2) —
  genuinely complete, even though `download_status.json` said otherwise at
  the time (flagged to `download_metadata` to correct). If its status still
  says `downloading` when you start, verify the file count yourself
  before trusting the status file blindly, the same way this gap was found.
- **`OFC_APA_CellGenomics2025`**: **resolved 2026-08-26** (was genuinely
  unresolved before then — the single-file-per-run pattern for 24/46 runs
  turned out to be a real barcode-read download bug, not a legitimate
  per-assay SRA convention). `download_metadata` completed a full
  re-download: 46/46 runs now verified present with correct file counts (168
  total `.gz` files, no missing runs, no anomalous counts). This study's
  FASTQ is genuinely complete for the first time in the collection's
  history — safe to build a samplesheet and submit real alignment for it now.
  It has not yet actually been submitted through the Nextflow pipeline as of
  this writing (only `Pineda2024_Cell` has real alignment runs so far) —
  `build_samplesheet.py` already covers this study, so this is just a matter
  of someone actually running Section 6a's 3 commands against it.

## 3. Per-study chemistry confirmation (also gates real work)

Neither study's exact 10x chemistry/kit version is confirmed yet — do this
before writing any Slurm script, by reading the paper's own methods (not
inferring from filenames or SRA's generic `library_strategy` field, which
doesn't record kit version):

- **`Pineda2024_Cell`** (PMID/DOI already in `samples.json` —
  `source_doi_or_pmid` currently reads `10.1016/j.cell.2024.02.031`, but see
  the open flag below): confirm exact 10x chemistry (3' v2/v3, or 5') from
  the paper's methods. Recent CellRanger versions auto-detect chemistry in
  most cases (`--chemistry=auto`, the default) — this is a lower-risk
  confirmation than the multiome question below, but still check, since
  auto-detection can silently pick the wrong chemistry on ambiguous data.
  **Open flag, check before trusting this DOI**: `verification`'s paper
  cross-check (2026-07-27, changelog) found this DOI may point to the wrong
  paper — the actual GSE174332 cohort might trace to a 2021 bioRxiv preprint
  instead. Confirm the correct paper before reading "its" methods.
- **`OFC_APA_CellGenomics2025`**: chemistry for both the snRNA-seq and
  snATAC-seq arms needs confirming from the paper
  (`10.1016/j.xgen.2025.101007`). **The multiome question is already
  resolved** — user confirmed via the paper's methods (2026-07-27, flagged to
  `download_metadata`) that RNA and ATAC come from **different nuclei pools**
  of the same donor's tissue, NOT a joint multiome capture. This means:
  **route to separate `cellranger count` (RNA) + `cellranger-atac count`
  (ATAC) runs, never `cellranger-arc`.** Do not revisit this — it was
  confirmed from the paper's own text, not inferred.

## 4. Tooling already available on HTCF — no new installs needed for either study

Verified directly (2026-07-27), all under `rmlab`'s own software (no
exception/permission needed beyond the standing rmlab+azamat write scope):

| Tool | Path | Verified |
|---|---|---|
| CellRanger 8.0.1 | `/ref/rmlab/software/cellranger_8.0.1/cellranger-8.0.1/cellranger` | `--version` runs, reports `cellranger-8.0.1` |
| CellRanger 7.1.0 (alternate) | `/ref/rmlab/software/cellranger_7.1.0/cellranger-7.1.0/cellranger` | present |
| CellRanger-ATAC 2.1.0 | `/ref/rmlab/software/cellranger-atac/cellranger-atac-2.1.0/bin/cellranger-atac` | present |
| CellRanger-ARC 2.0.2 | `/ref/rmlab/software/cellranger-arc/cellranger-arc-2.0.2/bin/cellranger-arc` | present (not needed per Section 3's resolved multiome question, but noted in case a future study needs it) |
| RNA reference | `/ref/rmlab/software/cellranger_8.0.1/refdata-gex-GRCh38-2024-A` | already extracted, ready to use |
| RNA reference (alt) | `/ref/rmlab/data/10x_refs/refdata-gex-GRCh38-2020-A` | already extracted |
| RNA reference, **mouse** (mm10) | `/ref/rmlab/data/10x_mm10_data/refdata-gex-mm10-2020-A` | confirmed extracted (2026-08-19), standard `fasta/genes/pickle/reference.json/star` layout — needed for `Pineda2024_Cell`'s 5 mouse control runs, Section 5 |

**Not yet verified — check before submitting an ATAC job**: a *standalone*
`cellranger-atac`-compatible reference bundle (distinct from the
`cellranger-arc` joint reference at
`/ref/rmlab/data/10x_refs/refdata-cellranger-arc-GRCh38-2020-A-2.0.0`, which
is NOT compatible with standalone `cellranger-atac count` — different
reference format between the two tools). Search `/ref/rmlab` and other labs'
`/ref/*/data` for `refdata-cellranger-atac-GRCh38*` before assuming one
exists; if none is found, one may need to be built via
`cellranger-atac mkref` from a plain genome FASTA + GTF, which is a real,
non-trivial extra step — flag to the user if this is the case rather than
guessing at reference construction parameters.

## 5. Per-study source data and routing

### Pineda2024_Cell (snRNA-seq only, GSE174332, 66 GEO samples / 152 SRA runs)
- FASTQ location: `studies/Pineda2024_Cell/raw/fastq/*.fastq.gz`
- **Run-to-sample mapping required before alignment**: 152 runs map to only
  66 GEO samples (GSM accessions), meaning most samples span multiple
  sequencing runs that `cellranger count` needs pointed at together via its
  `--fastqs` argument (comma-separated directories) or a multi-row
  `libraries.csv`-equivalent — CellRanger aggregates all of a sample's lanes/
  runs automatically when given the shared sample name prefix, but the
  *mapping* from SRR run IDs to which GSM/sample they belong to must be
  derived first (via `samples.json`'s sample records, cross-referenced
  against SRA's run-to-experiment linkage — check via `efetch`/`esummary`
  against `sra`, not guessed from filename similarity alone).
- Route: `cellranger count --transcriptome=<GRCh38 ref> --fastqs=<dirs for this sample's runs> --sample=<name>`
- Output needed: both `filtered_feature_bc_matrix.h5` and
  `raw_feature_bc_matrix.h5` per sample — the raw one is a genuine bonus,
  since it directly supplies the true unfiltered droplet-space matrix this
  collection is otherwise missing for ambient-RNA correction (see
  `AMBIENT_RNA_RAW_DATA_AUDIT.md`).
- **Mixed-species warning (confirmed 2026-08-19, directly against
  `samples.json`'s `organism` field — do not re-derive this from filenames,
  the title strings below only became obviously mouse in hindsight):** 5 of
  the 152 runs are `Mus musculus` (C57BL/6 motor-cortex controls), NOT human
  — `SRR27867712`, `SRR27867713`, `SRR27867714`, `SRR27867715`,
  `SRR27867716` (titles `220616_BL6_MCX_snRNA-H10/H11/H12/A1/A2`), same
  paired-file (`_1`/`_2`) structure as the human runs, so nothing about the
  file layout itself flags them as different. **Route these 5 through
  `--transcriptome=<mm10 ref>` (Section 4), never the human GRCh38
  reference** — check every run's `organism` field before batching, don't
  assume a study is single-species just because its title/disease focus is
  human ALS. The other 149 runs (147 human ALS/FTLD/control + 2 GSE174332
  supplement) are `Homo sapiens`, route as above.

### OFC_APA_CellGenomics2025 (snRNA-seq + snATAC-seq, separate nuclei pools, PRJNA918304, 46 SRA runs)
- Species: confirmed 2026-08-19, all 46 records `Homo sapiens` — no
  mixed-species handling needed for this study.
- FASTQ location: `studies/OFC_APA_CellGenomics2025/raw/fastq/*.fastq.gz`
- Confirmed NOT multiome (Section 3) — process the RNA and ATAC runs as two
  entirely independent pipelines, matched only by donor ID for later
  donor/pseudobulk-level comparison (never per-nucleus).
- RNA runs: route to `cellranger count` (same as Pineda2024_Cell's pattern).
- ATAC runs: route to `cellranger-atac count` — **blocked on Section 4's open
  reference-bundle question** until resolved.
- Run-to-sample mapping: `samples.json`'s `sample_alias` field already
  encodes donor + assay type per run (e.g. `C9ALSnoFTLD1_snATAC`) — use this
  directly rather than re-deriving it; each `sample_alias` value maps to
  exactly one SRA run for this study (confirm this holds before assuming it,
  since it differs from `Pineda2024_Cell`'s one-sample-to-many-runs pattern).

## 6. Per-study pipeline stages (generic template)

**Superseded 2026-08-24 for the CellRanger RNA track** — steps 3-7 below
(renaming, batched submission, resource sizing, verifying, copying back,
cleanup) are now what the Nextflow pipeline does automatically. See Section
6a for the actual commands. Steps 1, 2, and 8 are still real manual work —
the pipeline doesn't decide chemistry/completeness for you, and doesn't talk
to `conversion` for you.

1. Confirm download completeness (Section 2) and chemistry (Section 3) for
   the specific study — do not skip even if this doc says something was
   already confirmed; re-verify against current `download_status.json`/
   `CHANGELOG.jsonl` state, since time may have passed since this was written.
   **Also confirm organism per run/sample from `samples.json` before batching
   anything** — do not assume a study is single-species just because its
   title/disease focus is human. `Pineda2024_Cell` is the confirmed real
   case (5 of 152 runs are `Mus musculus` controls, Section 5) found only by
   checking the field directly, not from filenames or run titles.
2. Regenerate the samplesheet (Section 6a) — this is what now does Section
   5's run-to-sample mapping and species routing automatically, reading
   directly from `samples.json` and `raw/fastq/`'s actual file counts rather
   than trusting a status field. Re-run it whenever more runs get
   barcode-fixed or a study's download state changes; it's idempotent.
3-7. ~~Rename FASTQ / submit per-sample jobs / size resources / verify
   `web_summary.html` / copy back / clean up scratch~~ — handled by
   `driver.sbatch` + `sync_to_lts.sh` (Section 6a). Still true and still your
   job: actually look at `web_summary.html`'s real metrics before trusting a
   sample is done — a completed Nextflow task means the process exited 0, not
   that the biology looks right.
8. Hand off: once a study's samples are all aligned and verified, add a new
   per-study entry to `PIPELINE_INSTRUCTIONS.md` Section 3 describing exactly
   where the matrices live (mirroring the existing entries' format), and flag
   `conversion` via the changelog that the study is ready — `conversion`
   should not start on either of these two studies until this handoff happens
   (see Section 8's cross-role dependency).

## 6a. Running the Nextflow pipeline

Pipeline lives at
`EXTERNAL_DATASETS/scripts/alignment/nextflow_cellranger/`. Three real
commands, run in order:

```bash
# 1. Regenerate the samplesheet (idempotent, safe to re-run anytime;
#    reads samples.json + raw/fastq/ directly, not any status file)
/ref/rmlab/software/azamat/als_pipeline_env/bin/python3 \
    scripts/alignment/nextflow_cellranger/samplesheets/build_samplesheet.py

# 2. Submit the driver as its own Slurm job (survives disconnection --
#    do not run this under nohup/tmux on the login node instead)
sbatch scripts/alignment/nextflow_cellranger/driver.sbatch \
    scripts/alignment/nextflow_cellranger/samplesheets/cellranger_rna_samplesheet.csv \
    /scratch/rmlab/rmlab_shared3/azamat/nf_cellranger_run   # outdir: /scratch, never /lts

# 3. Once the driver job completes, sync results back -- from the LOGIN
#    NODE, never from inside a Slurm job (same /lts read-only-on-compute-
#    nodes rule as everywhere else in this pipeline)
./scripts/alignment/nextflow_cellranger/sync_to_lts.sh \
    /scratch/rmlab/rmlab_shared3/azamat/nf_cellranger_run
```

If the driver job dies partway (hits its own 72h limit, node failure,
whatever) — just `sbatch` it again with the same samplesheet/outdir.
`-resume` is on by default in the script; already-completed samples are not
redone. This is the same "don't repeat finished work" principle
`download_metadata`'s worker-pool claim files already enforce for FASTQ
downloads, just via Nextflow's own resume cache instead of a hand-built
claim mechanism.

**What the pipeline does NOT do for you**: decide whether a study's download
is actually complete (step 1 above), or talk to `conversion` (step 8). It
also doesn't currently cover the ATAC arm (no reference bundle yet, Section
4) or ADD a study to its own scope — the samplesheet builder is hardcoded to
`OFC_APA_CellGenomics2025` + `Pineda2024_Cell` today; extending it to a future
study means editing `build_samplesheet.py`, not just re-running it.

## 7. Output directory layout

```
studies/<study_id>/
  raw/
    fastq/                          <- existing, do not modify
    counts/
      <sample_id>/
        filtered_feature_bc_matrix.h5
        raw_feature_bc_matrix.h5
        web_summary.html
  samples.json                      <- existing, do not modify (download_metadata's file)
```

For the CellRanger RNA track this is what `sync_to_lts.sh` (Section 6a)
produces automatically — confirmed to match this exact layout via a real
validation run, 2026-08-24, not just designed to match it on paper.

## 8. Coordination-protocol integration

- New role key: `alignment`. Own status file: `alignment_status.json`
  (coordination root). Phase vocabulary:
  `not_started -> chemistry_confirmed -> aligning -> aligned -> blocked`.
- Own output location: `studies/<id>/raw/counts/*` — you own this, others
  read-only, same pattern as `conversion` owning `processed/`.
- **Cross-role dependency**: don't start real alignment work on a study until
  `download_metadata` shows it fully `downloaded` (verify yourself per
  Section 2 — don't trust the status file blindly, given the exact gaps
  already found this session). `conversion` should not touch
  `OFC_APA_CellGenomics2025`/`Pineda2024_Cell` until you show `aligned` for
  them — this mirrors the existing `conversion`-waits-on-`download_metadata`
  rule already in `PROTOCOL.md`.
- **Known gap, not yet built**: `orchestrator_check.py`'s cross-session
  phase-contradiction check does not yet know about `alignment` specifically
  (e.g. it won't flag `conversion` claiming a study is `converted` while
  `alignment` hasn't reached `aligned` for it). Until that's added, don't
  rely on the orchestrator to catch this class of contradiction for these
  two studies — check manually.

## 9. SRP566214_dataset — long-read track (added 2026-08-19)

Separate from Sections 2-7 on purpose — none of the CellRanger machinery
applies here. Do not skip Section 1's chemistry-gate discipline just because
this is a small study (8 runs).

**What's known already** (from `samples.json`, all 8 records — check it
yourself before starting, this is a summary not a substitute):
- Species: confirmed 2026-08-19, all 8 records `Homo sapiens` (iPSC-derived
  motor neurons) — no mixed-species handling needed for this study.
- ONT PromethION (`instrument_model`), `library_source: transcriptomic`,
  `assay_type: long-read RNA-seq`, `extra_library_kit_note: "ONT ligation
  sequencing kit"` — a ligation kit implies **cDNA** sequencing (PCR-cDNA or
  direct cDNA), not ONT's separate direct-RNA kit, but confirm this from the
  paper's methods (DOI `10.7554/eLife.95062`) rather than trusting the
  inference — direct-RNA vs. cDNA changes the correct `minimap2` preset.
  `literature/NOTES.md` already has this paper's full text cross-checked
  against the 8-sample design (E8/E5 x NES/Control x 2 replicates, MATCH) —
  read it before re-deriving the design from scratch.
- `extra_genome_build_note: "hg19 (per GEO Sample_data_processing)"` — the
  **original authors** aligned to hg19. This collection's standard elsewhere
  is GRCh38 (Section 4's references). Decide explicitly whether to re-align
  to GRCh38 for collection consistency (recommended, but means results won't
  be a direct re-derivation of the paper's own coordinates) or match hg19 —
  flag to the user if unsure, don't default silently either way.
- Study's actual scientific point is **TDP-43-driven cryptic splicing**
  (NES-nanobody-induced mislocalization) — matching this collection's
  existing interest in cryptic-exon/splicing signal (see the GSE296714/
  LeafCutter thread in `neurodegen-commons`, a related downstream consumer
  project — [[project_neurodegen_commons]] if you have access to this
  session's memory). This means a plain gene-count table alone would likely
  under-serve the actual purpose — a splice-aware alignment preserving
  junction-level output (BAM + junction calls, not just gene counts) is
  probably the more useful target. This is a genuine open design question,
  not a settled spec — decide and document your reasoning, don't just default
  to a bulk-RNA-seq-style gene-count matrix because that's what Section 2's
  format-policy table already has a slot for.
- **Possible shortcut worth checking first**: `samples.json`'s
  `extra_companion_dataset_note` says GEO series `GSE290441` already hosts a
  processed supplementary file, `GSE290441_tdp43_all_chr.counts.tsv.gz`
  (gene-level counts), not yet downloaded. Downloading this (via
  `download_metadata`, since it doesn't own raw FASTQ processing, or by you
  if faster) could serve as a validation target for your own alignment output,
  or — if it turns out to already have the granularity this study needs — may
  reduce or remove the need to align from FASTQ at all. Check it before
  assuming a full realignment is necessary.

**Tooling — not yet verified on HTCF, check before assuming availability**:
`minimap2` and `samtools` (commonly available via conda/module, unlike
CellRanger's dedicated install) — confirm a working version exists or install
into `/ref/rmlab/software/azamat/` (same convention as the DecontX R env).
No GRCh38 long-read-appropriate reference/GTF has been confirmed for this
study yet — check `/ref/rmlab` first before assuming one needs building.

**Format-policy gap**: `PIPELINE_INSTRUCTIONS.md` Section 2's format table has
no row for long-read RNA-seq / splice-aware output — same class of gap as the
DivergentC9 standalone-snATAC gap flagged 2026-08-19. Once you've decided the
target output shape above, that gap should get closed with a new table row,
not left implicit.

**Cross-role dependency**: same rule as Section 8 above — `conversion` should
not touch `SRP566214_dataset` until you show `aligned` (or whatever the
agreed-upon output state ends up being called) for it.

## 10. Bulk RNA-seq alignment track (added 2026-08-21, no study in scope yet)

**Not active work.** No study currently in the collection needs this — every
bulk study we have already arrived with a processed count matrix from its
original authors (confirmed directly against every bulk study's `raw/`
contents; see `PIPELINE_INSTRUCTIONS.md` Section 9 for the harmonization work
that already-deposited data needs, which is a `conversion`-role task, not
this one). This section exists so that if a future study is added as
FASTQ-only bulk RNA-seq (no deposited matrix), the alignment role has a ready
recipe instead of improvising one under time pressure.

**Specified parameters** (per explicit user instruction, 2026-08-21):
- Aligner: **STAR 2.7.11b**
- Genome: **GRCh38** primary assembly
- Annotation: **GENCODE v44**

**Deliberately does NOT match `neurodegen-commons`'s own bulk STAR route**
(their Route 1 uses GENCODE v26, specifically chosen so their definition of
"cryptic" — an unannotated splice junction — stays consistent between their
freshly-reprocessed studies and their recount3-reused studies, which are also
v26). Confirmed as an intentional choice, not an oversight, when this section
was written — v44 is more current/complete, at the cost of this collection's
own bulk alignment output not being directly junction-comparable to
`neurodegen-commons`'s existing corpus. If a future study aligned under this
section ever needs to feed into their consensus/splicing work, re-align with
v26 rather than assuming v44 output is interchangeable.

**Recommended run parameters** (adapted from `neurodegen-commons`'s own proven
Route 1 recipe — sound engineering choices independent of which GENCODE
version is used, so reused here rather than re-derived): two-pass mode
(`--twopassMode Basic`, improves sensitivity to novel/cryptic junctions on the
second pass), `--quantMode GeneCounts`, `--sjdbOverhang 100`, `--outSAMtype
None` (do not retain the BAM — same storage-discipline reasoning as the rest
of this pipeline; the alignment coordinates aren't needed downstream, only
the counts and junctions are). **Keep both output tables per sample**:
`ReadsPerGene.out.tab` (gene counts) and `SJ.out.tab` (splice junctions) — the
junction file is not optional even though the *"how is single-cell alignment
different"* answer below explains why CellRanger doesn't produce an
equivalent; for bulk, dropping it would silently remove this collection's
only source of junction-level detail for whatever study ends up here.

**Output location**: `studies/<study_id>/raw/counts/<sample_id>/` — same root
convention as the CellRanger track (Section 7), just with
`ReadsPerGene.out.tab`/`SJ.out.tab` instead of the `.h5` files. `conversion`'s
Section 9 bulk-harmonization pass picks up from here to produce the
collection's shared Parquet+TSV format — this section's job stops at
producing the raw STAR output, same handoff boundary as Section 1 already
establishes for the CellRanger track.

**How this differs from the CellRanger track (Sections 2-7) — read before
assuming the two tracks are interchangeable or that one is just a simpler
version of the other:**
- **Unit of quantification.** Bulk STAR collapses each *sample* (a tube of
  RNA from potentially millions of pooled cells/nuclei) into one gene-count
  vector — one row of output per sample. CellRanger's whole purpose is the
  opposite: preserving *per-cell* resolution, producing thousands of
  individual cell-level count vectors per sample. This is the core
  difference everything else follows from.
- **Barcode/UMI demultiplexing.** 10x reads carry a cell barcode + UMI in a
  separate read (e.g. 16bp CB + 12bp UMI for 3' v3) that must be
  error-corrected and used to (a) assign each read to a specific cell and
  (b) collapse PCR/optical duplicates via UMI counting, before any gene
  counting happens. Standard bulk RNA-seq (as deposited by every study in
  this collection) has no such step — there is no barcode read at all, only
  cDNA reads.
- **Cell calling.** Single-cell/nucleus data needs a statistical step
  distinguishing real cell-containing droplets from ambient-RNA-only empty
  droplets (CellRanger does this internally). Bulk has no droplets and no
  analogous step — every sample is real by construction.
- **What's under the hood.** CellRanger actually uses STAR internally for
  the exonic/intronic alignment step, wrapped with the barcode/UMI/cell-
  calling logic above plus its own secondary analysis (PCA, clustering,
  UMAP) and its own reference package format (`cellranger mkref` output —
  `fasta/genes/star/pickle/reference.json`, confirmed for the mm10 reference
  added to Section 4). You cannot point plain STAR at 10x FASTQs and get a
  usable single-cell result — you'd lose the barcode/UMI/cell-calling logic
  entirely. (`STARsolo`, a STAR run mode built specifically to replicate
  CellRanger's counting logic, is the actual bridge between the two — not
  used by this pipeline's CellRanger track, noted here only so a future
  reader doesn't assume "STAR" always means the plain-bulk invocation this
  section describes.)
- **Junction/splicing output.** Bulk STAR's `SJ.out.tab` is a simple,
  complete per-sample junction table — the raw material this collection's
  (and `neurodegen-commons`'s) cryptic-splicing detection work depends on.
  CellRanger does not produce an equivalent simple junction table as part of
  its standard output — single-cell alignment as currently practiced by this
  role's Sections 2-7 does not give the same splicing-detection capability
  bulk STAR does. Don't assume a converted single-cell study can substitute
  for a bulk study in any junction-level analysis.
- **Reference format.** CellRanger needs its own pre-built reference package
  (see above); plain bulk STAR just needs a genome FASTA + GTF and a
  `STAR --runMode genomeGenerate` index — the two reference formats are not
  interchangeable even though both ultimately run STAR.
