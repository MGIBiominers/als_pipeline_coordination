# ALS Pipeline Coordination

Coordination layer for an **agentic pipeline that downloads, processes and validates external ALS (amyotrophic lateral sclerosis) datasets** for MGI. Several independent Claude Code sessions ("agents"), each with one narrow role, work concurrently on a shared dataset collection (`EXTERNAL_DATASETS`) on the HTCF cluster at WashU, with a mirrored copy on RIS. This repository holds the protocol, the standing instructions each agent follows, and the orchestrator script.

## How the pipeline works

Raw studies (GEO, CELLxGENE, SRA, Zenodo, and others) move through four stages. Each stage is owned by one agent, and a separate set of agents independently checks the work of the stages before them.

```
download_metadata ──> alignment (FASTQ-only studies) ──> conversion ──> standardized h5ad / h5mu / parquet
        │                         │                          │
   verification            downstream_verification ──────────┘
 (checks downloads            (checks alignment and
  and metadata)                conversion output)
```

There is no live channel between agents. They coordinate only through shared files and strict ownership rules:

- **One owner per file.** Only the owning agent writes it. Anyone else who finds a problem flags it rather than editing.
- **Append-only changelog.** Every agent logs what it did and reads everything past its own checkpoint at the start of each work session.
- **Status and task ledgers.** Each agent keeps a status file with one phase per study and a ledger of its current task, so "in progress", "stalled" and "not started" can be told apart.
- **Advisory locks** on long-running or destructive operations.
- **Dual-write rule.** Every change to the dataset tree is mirrored from HTCF to RIS through a single script that keeps a history on both sides. A sync check then confirms the two copies match.

See [`PROTOCOL.md`](PROTOCOL.md) for the full rules.

## The agents

| Agent | Purpose |
|---|---|
| `download_metadata` | Downloads raw study data and builds and maintains per-study metadata (`samples.json`, `all_samples.tsv`, `studies.tsv`, `CATALOG.md`). |
| `alignment` | Turns FASTQ-only studies into count matrices for conversion to pick up: CellRanger through a Nextflow pipeline for single-cell studies, a long-read track for ONT data, and STAR for bulk RNA-seq. See [`ALIGNMENT_INSTRUCTIONS.md`](ALIGNMENT_INSTRUCTIONS.md). |
| `conversion` | Converts raw downloads into standardized `.h5ad` / `.h5mu` / `.parquet` files with a consistent `obs` schema and canonical vocabulary columns (disease status, tissue, cell type, genotype). See [`PIPELINE_INSTRUCTIONS.md`](PIPELINE_INSTRUCTIONS.md). |
| `verification` | Verifies the downloader's work: raw-data integrity and metadata accuracy, including a cross-check of per-sample values against each paper's own text and supplementary materials. See [`PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md`](PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md). |
| `downstream_verification` | Independently re-checks what was built from the raw data: converted-file structure and schema, DecontX correctness, and alignment QC (mapping rates, reference build, chemistry, species routing). |
| `orchestrator` | Not a working agent. It watches the others by reading shared state, reporting stalled sessions, stale locks, cross-agent contradictions and open blockers. It assigns tasks through the changelog and never edits another agent's files. See [`orchestrator_check.py`](orchestrator_check.py). |

## What is in this repository

- `PROTOCOL.md` is the coordination protocol: roles, file ownership, phase vocabulary, changelog, locks and orchestrator checks.
- `PIPELINE_INSTRUCTIONS.md`, `ALIGNMENT_INSTRUCTIONS.md` and `PAPER_METADATA_CROSSCHECK_INSTRUCTIONS.md` are the standing specs for conversion, alignment and verification.
- `conversion_process.md` documents the conversion process.
- `BRIEFING.md` and `NUDGE_*.md` are the onboarding briefings given to each agent.
- `orchestrator_check.py` is the health-check script.
- `checkpoints/` holds each agent's last-read position in the changelog.

Live working state is intentionally not published here: the per-agent status and task files, the changelog, and the generated reports and audits. Some documents refer to those files.
