# Briefing — paste into each of your 3 pipeline sessions

A coordination layer now exists for the shared EXTERNAL_DATASETS collection,
since the download/metadata, conversion, and verification sessions all edit
files in the same directory tree concurrently with no channel between them.

Read the full protocol now:

```
ssh <user>@login.htcf.wustl.edu 'cat /lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination/PROTOCOL.md'
```

Your role in this system is **`<<ROLE>>`** — one of `download_metadata`,
`conversion`, `verification` (pick the one matching what this session does).

Follow the protocol from now on: you own exactly one status file
(`<<ROLE>>_status.json` at the coordination root above) and must never write
another session's owned files directly (see the ownership table) — flag
issues instead. At the start of each work session, check
`CHANGELOG.jsonl` for anything past your checkpoint
(`checkpoints/<<ROLE>>.txt`); at the end, append your own changelog line,
update your own status file, and advance your checkpoint.

Your status file was seeded by a separate orchestrating session from existing
docs, not by you — treat its contents as a starting draft to correct, not
ground truth.
