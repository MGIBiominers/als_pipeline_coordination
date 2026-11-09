# Cross-session coordination protocol

**Read this before touching any shared file.** Independent Claude Code
sessions work on the same dataset collection concurrently:

| Role key            | Job |
|----------------------|-----|
| `download_metadata`  | Downloads raw study data from GEO/CELLxGENE/SRA; builds and maintains per-study metadata |
| `conversion`         | Converts raw downloads into standardized h5ad/h5mu/parquet formats per `PIPELINE_INSTRUCTIONS.md` |
| `verification`       | **Scope narrowed 2026-09-18** — verifies `download_metadata`'s work only: downloaded raw data integrity and metadata correctness (`samples.json`/`all_samples.tsv`/`studies.tsv` accuracy, including the `paper_crosscheck` cross-check against each paper's own text/supplementary materials). Does **not** check `conversion`'s or `alignment`'s output — see `downstream_verification` below. (Before this split, `verification` covered both; its pre-split history checking conversion output remains valid, just not its ongoing job.) |
| `alignment`          | Added 2026-07-27. Turns FASTQ-only studies into usable output for `conversion` to pick up, per `ALIGNMENT_INSTRUCTIONS.md`. `OFC_APA_CellGenomics2025`/`Pineda2024_Cell` via CellRanger — as of 2026-08-24, run through the Nextflow pipeline at `EXTERNAL_DATASETS/scripts/alignment/nextflow_cellranger/`, not hand-written per-sample sbatch scripts; see `ALIGNMENT_INSTRUCTIONS.md` Section 6a. `SRP566214_dataset` (added 2026-08-19) is a separate long-read track — ONT data, no CellRanger, see `ALIGNMENT_INSTRUCTIONS.md` Section 9. `GSE182976_dataset` (added 2026-09-15) is the first use of the bulk STAR track, Section 10. This role does not do format conversion itself. |
| `downstream_verification` | **Added 2026-09-18**, split off from `verification`'s original combined scope. Independently checks `conversion`'s converted output (`.h5ad`/`.h5mu`/`.parquet` structural integrity, `obs` schema correctness including the canonical vocabulary columns, DecontX correctness) **and** `alignment`'s raw output (CellRanger/STAR QC metrics — mapping rates, reference builds, chemistry choices — `raw/counts/`/`raw/alignments/` deliverables). This second half (independently checking `alignment`'s own output, not just what `conversion` derives from it) is new — before this role existed, nobody independently re-checked `alignment`'s claims the way `verification` already re-checked `download_metadata`'s and `conversion`'s. See Section 2b below for the full scope definition. |
| `orchestrator`       | Not a working session — a deterministic, non-AI script (`orchestrator_check.py`) run on a schedule (macOS launchd, since no cloud-scheduled agent can reach HTCF) that reads everything below and writes a health-check report. Never edits any working role's own files. |

Two separate roots matter here — don't confuse them:
- **Dataset collection root:** `/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS`
  — contains ONLY the actual data/metadata (`studies/` including each study's own
  `raw/`, `processed/`, `literature/`; `samples.json`; `studies.tsv`;
  `all_samples.tsv`; `build_summary.json`; `CATALOG.md`; `schema/`). Kept strictly
  dataset-related — no agent instructions or reports belong here.
- **Coordination root:** `/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination`
  — ALL agent instructions and reports live here: `PROTOCOL.md`, `CHANGELOG.jsonl`,
  the five `*_status.json` files, the five `*_tasks.json` per-role activity
  ledgers (four each until `downstream_verification` was added 2026-09-18),
  `checkpoints/`, `locks/`, `PIPELINE_INSTRUCTIONS.md`,
  `ALIGNMENT_INSTRUCTIONS.md`, `PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md`,
  `METADATA_QC_FLAGS.md`, `conversion_process.md`, `AMBIENT_RNA_RAW_DATA_AUDIT.md`/`.tsv`,
  `TASK_*.md` task briefs, `BRIEFING.md`. These 6 files moved out of the dataset
  collection root on 2026-07-27 (at the user's explicit request to consolidate
  everything agent-related in one place) — a one-line pointer stub was left at
  each old location. All paths below are given relative to THIS root unless
  stated otherwise.

There is no live channel between the three sessions — they coordinate purely
through these files plus the ownership rules below. Follow both.

## 1. File ownership — only the owner writes

A file with one owner can never have a lost-update race. If you are not the
listed owner, propose changes via your own status file / flag doc instead of
editing the file directly.

| File | Owner | Others may |
|---|---|---|
| `samples.json` (per study), `all_samples.tsv`, `studies.tsv`, `build_summary.json` (all in the dataset collection root) | `download_metadata` | read; flag issues in `verification`'s own doc |
| `studies/<id>/processed/*` (per-study, dataset collection) | `conversion` | read |
| `studies/<id>/literature/*` (per-study, dataset collection) | `verification` | read |
| `studies/<id>/raw/counts/*` (per-study, dataset collection) | `alignment` | read |
| `CATALOG.md` (dataset collection) | `download_metadata` | read; do not append/edit — put your own narrative in your own doc and let the owner link to it |
| `download_status.json`, `download_metadata_tasks.json`, `AMBIENT_RNA_RAW_DATA_AUDIT.md`/`.tsv` (coordination root) | `download_metadata` | read only |
| `conversion_status.json`, `conversion_tasks.json`, `conversion_process.md` (coordination root) | `conversion` | read only |
| `verification_status.json`, `verification_tasks.json`, `METADATA_QC_FLAGS.md`, `PAPER_METADATA_CROSSCHECK.md` (coordination root) | `verification` | read only |
| `alignment_status.json`, `alignment_tasks.json` (coordination root) | `alignment` | read only |
| `downstream_verification_status.json`, `downstream_verification_tasks.json` (coordination root, added 2026-09-18) | `downstream_verification` | read only |
| `CHANGELOG.jsonl` (coordination root) | shared, append-only | anyone may APPEND a line; never rewrite existing lines |
| `checkpoints/<role>.txt` (coordination root) | that role only | read only |
| `locks/<study_id>.json` (coordination root) | whoever created it | others must not delete someone else's lock |
| `PIPELINE_INSTRUCTIONS.md`, `PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md`, `ALIGNMENT_INSTRUCTIONS.md`, `BRIEFING.md` (coordination root) | `orchestrator` / edited only at explicit user request | read; these are **standing** spec docs, referenced indefinitely, not per-role working state — don't edit them as part of normal work |
| `TASK_*.md` (coordination root) | `orchestrator` / edited only at explicit user request | read while the task is open; **the orchestrator deletes each one once its assigned work is confirmed done** (see below) — unlike the standing instruction docs above, these are one-off briefs, not permanent references |
| `ORCHESTRATOR_REPORT.md`, `orchestrator_state.json`, `checkpoints/orchestrator.txt` (coordination root) | `orchestrator` (the scheduled `orchestrator_check.py` script — see below) | read only |

If a change genuinely needs to land in a file you don't own (e.g. verification
found a wrong `bioproject` value in `studies.tsv`), write it to
`METADATA_QC_FLAGS.md` (or append a changelog event with
`action: "flag_for_owner"`) rather than editing the file yourself. The owning
session applies it and closes the flag.

## 2. Per-study phase vocabulary

Each status JSON tracks one phase per `study_id` from its own role's
perspective, using exactly these values so cross-session reads are unambiguous:

- `download_metadata` phases: `not_started -> downloading -> downloaded -> metadata_normalized`
- `verification` phases: `not_queued -> verifying -> verified -> verify_failed`
- `conversion` phases: `not_started -> converting -> converted -> blocked -> out_of_scope`
- `alignment` phases: `not_started -> chemistry_confirmed -> aligning -> aligned -> blocked`
- `downstream_verification` phases (added 2026-09-18, same vocabulary as `verification`, applied to `conversion`/`alignment` output instead of downloads): `not_queued -> verifying -> verified -> verify_failed`. Track per study; if a study needs both its alignment output and its conversion output checked, cover both in the same study's `note` rather than inventing per-stage sub-keys.

Any phase other than the "happy path" end state (`metadata_normalized`,
`verified`, `converted`) MUST carry a non-null `note` explaining why (or
`blocked_reason` for `conversion`'s `blocked`). Never leave a stalled state
unexplained — that is exactly the information the other sessions need.

**Cross-role dependency:** `conversion` should not start converting a study
until `download_metadata` shows `downloaded` (or better) for it, and should
treat `verification`'s `verify_failed` for it as a hard stop pending a fix on
the raw/metadata side — check both other sessions' status files for a study
before starting non-trivial work on it, not just your own. **Updated
2026-09-18**: `conversion` and `alignment` should likewise treat
`downstream_verification`'s `verify_failed` for a study as a hard stop on
their own output pending a fix — that role now owns re-checking their work,
not `verification`.

**`alignment`'s dependencies**: don't start real alignment work on a study
until `download_metadata` shows it fully `downloaded` — and given real gaps
already found this session (a study's status file claiming completion when
it wasn't, and vice versa), verify against actual `raw/fastq/` file counts
yourself rather than trusting the status file blindly (see
`ALIGNMENT_INSTRUCTIONS.md` Section 2 for the specific per-study state as of
2026-07-27). `conversion` should not touch `OFC_APA_CellGenomics2025`/
`Pineda2024_Cell` until `alignment` shows `aligned` for them — same shape as
the `conversion`-waits-on-`download_metadata` rule above. **Known gap**:
`orchestrator_check.py`'s automated phase-contradiction check does not yet
compare `alignment`'s phase against `conversion`'s for these two studies —
this has to be checked manually until that's built. **Second known gap,
added 2026-09-18**: that same script's cross-contradiction check currently
compares `verification_status.json`'s `verify_failed` against
`conversion_status.json` (see Section 5) — now that conversion-output
checking has moved to `downstream_verification`, the script needs updating
to read `downstream_verification_status.json` for that comparison instead.
`orchestrator_check.py` lives locally on the user's Mac (the launchd-scheduled
copy), not on HTCF, so this can't be fixed from a session working the
coordination files alone — flagging it here so it isn't silently missed
until someone notices the check has gone stale.

## 2b. `downstream_verification`'s scope, precisely (added 2026-09-18)

Split off from `verification` because analysis showed a real gap: `alignment`'s
own output (CellRanger/STAR QC metrics, mapping rates, reference/chemistry
choices) was never independently re-checked by anyone — only self-reported by
`alignment` itself, occasionally spot-checked ad hoc by the orchestrator.
Everything below is now `downstream_verification`'s job, not `verification`'s:

- **Conversion output**: for each study `conversion` marks `converted` (or
  `converted_partial`), independently confirm the `.h5ad`/`.h5mu`/`.parquet`
  file(s) actually on `/lts` match what the changelog/`conversion_status.json`
  claims — shape, `obs`/`var` schema, the canonical vocabulary columns
  (`disease_status_canonical`/`tissue`/`cell_type`/`genotype_canonical`) both
  present and correctly copied from `samples.json` (see
  `PIPELINE_INSTRUCTIONS.md` Section 4a), DecontX correctness where it
  applies. This is the same checklist `verification` used before the split —
  moved here wholesale, not redesigned.
- **Alignment output**: for each study `alignment` marks `aligned`,
  independently confirm the real deliverables exist and look right — QC
  metrics (mapping rate, cell counts, valid-barcode percentage for CellRanger;
  uniquely-mapped percentage for STAR) are in a plausible range, not just
  present; the correct reference build/version was actually used (e.g. catch
  a GRCh38-2024-A vs. exact-GENCODE-v44 substitution before it ships); species
  routing is correct for mixed-species studies. This is new work with no
  pre-split precedent — the first real target is `GSE182976_dataset`'s STAR
  output and any of the CellRanger studies already marked `aligned`.
- **Still `verification`'s job, not this role's**: whether the raw
  *downloaded* data and its metadata are correct (`samples.json`/
  `all_samples.tsv`/`studies.tsv` accuracy, the `paper_crosscheck` field,
  anything in `METADATA_QC_FLAGS.md`). If something looks wrong upstream of
  alignment/conversion — e.g. a raw file that doesn't match its
  `download_manifest.json` — flag it via `CHANGELOG.jsonl` for
  `download_metadata` or `verification` to pick up rather than fixing it here;
  this role's job is checking what got *built from* the raw data, not the raw
  data's own correctness.

**Transition note**: `verification`'s pre-2026-09-18 history checking
conversion output (see `METADATA_QC_FLAGS.md`'s "Conversion-integrity QC
pass" section and many `CHANGELOG.jsonl` entries) remains valid — nothing
needs re-checking just because of the role split. `downstream_verification`
starts fresh from studies converted/aligned on or after its creation, plus
whatever backlog it chooses to work through; it does not need to redo
`verification`'s prior work from scratch.

**`verification` also tracks a second, independent field per study**:
`paper_crosscheck` (`not_started -> in_progress -> matches | mismatch_found |
no_crosswalk | source_inaccessible`) — added 2026-07-27, see
`PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md` at this coordination root for
the full brief. This tracks whether per-sample metadata *values* have been
checked against each paper's own supplementary materials, which is separate
from (and can lag well behind) the main `phase` field above — a study can be
structurally `verified` while its `paper_crosscheck` is still `not_started`.

## 2a. How task assignments actually reach a role (added 2026-07-28)

Two patterns, by size — both ultimately visible only through `CHANGELOG.jsonl`,
since that's the one file every role reads from its checkpoint forward:

- **Small, targeted asks**: the full instructions live directly in a
  changelog line's `note` field (`action: "task_assigned"` or
  `"flag_for_owner"` for a correction to existing work). No separate file —
  the changelog line *is* the task. Most follow-up asks are this size.
- **Larger assignments**: a dedicated brief gets written as its own
  `TASK_*.md` file at the coordination root (e.g.
  `TASK_ambient_rna_raw_data_audit.md`, since deleted — see below), with a
  short changelog line pointing to it. Used when the full spec is too large
  for one log line.

**`TASK_*.md` files are deleted once their assigned work is confirmed
done** — verify the actual deliverable exists first (e.g. don't delete a task
brief for an audit until the audit's output file is confirmed populated),
then remove the brief. The permanent record of what was assigned and what
happened lives in `CHANGELOG.jsonl` regardless (append-only, never deleted)
— the brief itself is scratch, not the record. This is different from
`PIPELINE_INSTRUCTIONS.md`/`ALIGNMENT_INSTRUCTIONS.md`/
`PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md`, which are **standing** specs a
role keeps referencing indefinitely — those never get deleted just because
some work under them finished; only the task-assignment briefs following the
`TASK_*.md` naming convention do.

## 3. Changelog — the "what changed since I last looked" mechanism

`CHANGELOG.jsonl` (coordination root) is append-only, one JSON object per line:

```json
{"ts": "2026-07-17T18:40:00Z", "session": "conversion", "action": "converted", "study_id": "HammellOneill2025_CellReports", "files": ["studies/HammellOneill2025_CellReports/processed/HammellOneill2025_CellReports.h5ad"], "note": "26,704 obs x 37,786 vars, 6 GSMs concatenated"}
```

Required fields: `ts` (ISO 8601 UTC), `session` (one of the working role
keys), `action` (short verb: `downloaded`, `verified`, `verify_failed`,
`converted`, `blocked`, `flag_for_owner`, `status_update`, `task_started`,
...), `study_id` (or `null` for collection-wide events), `note`. `files` is
optional (paths relative to the dataset collection root, e.g.
`studies/<id>/processed/...`).

**At the start of every work session/loop iteration:**
1. Read your own `checkpoints/<role>.txt` (a line number; `0` if you've never
   checked in).
2. Read `CHANGELOG.jsonl` from that line onward — this is everything that
   happened since you last looked, from either other session.
3. Skim the other sessions' status JSONs for any `study_id` you're about
   to touch, to catch a lock or a blocked/verify_failed state your own
   changelog tail might have missed (e.g. if you haven't checked in for a
   long time, reading full current status is more reliable than a long tail).
4. Check your own `<role>_tasks.json` (see below) for a leftover non-null
   `current_task` from a prior session that never got closed out (e.g. a
   crash) — resolve or explicitly re-open it rather than silently starting
   fresh work with a stale "currently working on" claim still sitting there.

**Before starting non-trivial work on any study/task** (added 2026-07-28,
after a real case where nobody could tell whether `download_metadata` was
actively working on two flagged issues or hadn't picked them up at all —
completed-only logging made "in progress," "not started," and "stalled" look
identical from the outside):
1. Set `current_task` in your own `<role>_tasks.json` (coordination root) —
   `{"description": "...", "study_id": "... or null", "started_at": "ISO8601"}`.
2. Append a `CHANGELOG.jsonl` line with `action: "task_started"` and the same
   description — the task file gives instant current-state visibility to
   anyone checking just your role; the changelog line gives the other roles
   visibility without them needing to know your task file exists.
This is per-*task*, not per-*session* — one work session commonly runs
several sequential tasks (e.g. `verification`'s batch-by-batch paper
cross-check), each bracketed by its own start and finish, not just one at
session start.

**When that task finishes:**
1. Move it from `current_task` into `recent_completed` (prepend; keep at most
   the last 20 entries — older history isn't lost, it's still in
   `CHANGELOG.jsonl`, this file is just a convenient recent-window view) with
   `completed_at` and a short `outcome`, and set `current_task` back to `null`.
2. Append one changelog line per meaningful action you took (not every file
   write — one line per study-level milestone is the right grain).
3. Update your own status JSON's `updated_at` and any changed per-study phases.
4. Advance your own checkpoint file to the new last-line number.
5. Release any locks you created and no longer need (see below).

## 4. Locks — advisory, not enforced

Before starting a long-running or destructive operation on a study (a
multi-hour Slurm conversion job, a re-download that will overwrite `raw/`, a
verification pass that reads the whole raw dataset), create
`locks/<study_id>.json` (coordination root):

```json
{"held_by": "conversion", "since": "2026-07-17T18:00:00Z", "note": "Slurm job 43607345, DivergentC9 resubmit"}
```

Check for an existing lock on a study before starting overlapping work on it;
if one exists and looks stale (job clearly would have finished — use your
judgment, there's no TTL enforcement), it's fine to proceed but say so in your
changelog line rather than silently overwriting the lock. Delete your own lock
file when the operation finishes or fails. Locks are a courtesy signal between
cooperating agents, not a mutex — never treat a lock as blocking a read.

## 5. The orchestrator check (`orchestrator_check.py`)

Runs every 4-6h via a launchd job on the user's Mac (a cloud-scheduled agent
cannot reach HTCF at all — no network path, no SSH credentials — so this has
to run somewhere with an already-authenticated SSH connection to HTCF).
Read-only with respect to the three roles' files; writes only its own
`ORCHESTRATOR_REPORT.md` / `orchestrator_state.json` / `checkpoints/orchestrator.txt`,
and appends one `check_completed` line to `CHANGELOG.jsonl` per run (allowed,
same as any role, per the append-only rule above).

Each run mechanically checks (no AI/LLM call involved):
- **New activity** since its own last checkpoint into `CHANGELOG.jsonl`.
- **Session health** per role: `active`, `never_briefed` (status file still at
  the original seed timestamp `2026-07-17T00:00:00Z` - meaning that session
  has never actually run this protocol yet), or `possibly_stalled` (status
  file's `updated_at` unchanged across >=2 consecutive checks).
- **Stale locks**: any `locks/*.json` older than 12h.
- **Cross-session phase contradictions**: e.g. `conversion_status.json` says a
  study is `converted` but `download_status.json` has an *explicit* per-study
  entry that isn't `downloaded`/`metadata_normalized` for it (deliberately
  ignores the free-text `_default_for_unlisted` catch-all - that's not a
  structured claim, treating it as one produced false positives on day one).
  Also flags `verification_status.json` reporting `verify_failed` while
  `conversion_status.json` still shows `converting`/`converted` for the same
  study. **Stale as of 2026-09-18** — this comparison should now read
  `downstream_verification_status.json` instead, per Section 2's second known
  gap above; not yet updated in the actual script.
- **Open blockers**: any `conversion_status.json` entry with `phase: "blocked"`,
  resurfaced every run until resolved (e.g. `Lall2025_CellStemCell`).
- Malformed changelog lines or lock `since` fields are skipped and reported,
  never allowed to crash the run or permanently wedge the checkpoint.
- **Cross-file consistency checks (Tier 1, added 2026-07-27)** — the first
  checks that read from the dataset collection root
  (`/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS`) directly, not just
  coordination state, since a real gap was found: status claims and actual
  dataset content had drifted apart multiple times with nothing catching it
  automatically. Both are cheap, local-file-only comparisons (no GEO calls,
  no opening large data files), so they run every cycle at no extra cost:
  - `check_converted_vs_processed`: any study `conversion_status.json` marks
    `converted` whose `studies/<id>/processed/` has no real output (empty, or
    only a housekeeping `.md` doc like a `CONVERSION_BLOCKED.md` flag file -
    those don't count), and the reverse (`not_started`/`blocked` with real
    output already present). Would have caught the Ho2021/Schweingruber/
    DivergentC9 stale-`converted`-claim episodes automatically.
  - `check_sample_count_consistency`: `build_summary.json`'s declared
    `n_samples` per study vs. the actual row count in `all_samples.tsv` for
    that `study_id`. Same comparison that caught the `Lall2025_CellStemCell`
    176-vs-88 bug during a one-time manual pass, now a standing check.
  Two deeper checks considered during design (assay-type reconciliation
  against `studies.tsv`'s free-text field; validating documented file paths
  actually exist) were deliberately deferred - both are fuzzier (prose/regex
  matching, not exact comparison) and were judged not worth the added
  false-positive risk for a first pass. Revisit if Tier 1 proves its worth.

Read `ORCHESTRATOR_REPORT.md` for the latest snapshot at any time - no need to
wait for a scheduled run if you want a check right now (`python3
orchestrator_check.py` from the coordination root does one immediately).

**Portability note:** HTCF's login-node system `python3` is 3.6.8 (no
`datetime.fromisoformat`, added in 3.7) - the script's timestamp parser is a
hand-rolled regex specifically because of this, not `fromisoformat`. Don't
"simplify" it back to `fromisoformat` without checking the login node's
Python version again first.

## 6. Bootstrapping note

This protocol was set up 2026-07-17 by a fourth, orchestrating Claude Code
session, seeded from the state visible at that time in `CATALOG.md`,
`conversion_process.md`, `METADATA_QC_FLAGS.md`, and `build_summary.json` (all
in the dataset collection). Per-study phases in the three status JSONs marked
`"unknown"` (or listed under `_default_for_unlisted`) were not confidently
derivable from those docs at seed time — the owning session should populate
them on its next run rather than trust a guess. The coordination root moved
from inside the dataset collection (`EXTERNAL_DATASETS/_coordination/`) to its
current standalone location on 2026-07-17, specifically to keep the dataset
collection strictly dataset-related.

**Second consolidation, 2026-07-27:** at the user's explicit request, all
remaining agent instruction/report docs that had stayed in the dataset
collection (`PIPELINE_INSTRUCTIONS.md`, `conversion_process.md`,
`METADATA_QC_FLAGS.md`, `PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md`,
`AMBIENT_RNA_RAW_DATA_AUDIT.md`/`.tsv`) moved here too. Only `CATALOG.md` and
`scripts/` (the actual executable pipeline code, plus its own docstring
references to `PIPELINE_INSTRUCTIONS.md` — those are prose citations only, not
runtime path reads, so the move didn't touch any script's behavior) stayed
in the dataset collection by explicit user choice. A one-line pointer stub
was left at each old path.

**Fifth role added, 2026-09-18:** `downstream_verification` split off from
`verification`'s original combined scope, per explicit user request, after
identifying that `alignment`'s own output was never independently re-checked
by anyone (see Section 2b for the full scope definition and rationale).
Seeded fresh at creation — `checkpoints/downstream_verification.txt` starts
at the `CHANGELOG.jsonl` line count at creation time (402), not 0, since
replaying all prior history predating this role's existence would be noise,
not useful context. `verification`'s own files/history are untouched by this
split; only its *going-forward* scope narrowed.
