#!/usr/bin/env python3
"""Deterministic health check over the ALS pipeline coordination state.
Run periodically (via launchd, see local orchestrator setup). No AI/LLM call
needed - staleness, stale locks, and phase contradictions are all mechanical
checks against the JSON schemas defined in PROTOCOL.md.
Owned by the 'orchestrator' role - see PROTOCOL.md's ownership table.
"""
import csv
import json
import os
import re
import glob
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
# Separate from ROOT (the coordination root) - these two new checks are the
# first thing this script reads from the actual dataset collection, not just
# its own coordination state. Read-only, same as everything else here.
DATASET_ROOT = "/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS"
SEED_TS = "2026-07-17T00:00:00Z"          # timestamp every status file was seeded with
STALE_STREAK_THRESHOLD = 2                 # consecutive unchanged checks before flagging "possibly stalled"
STALE_LOCK_HOURS = 12

ROLES = ["download_metadata", "conversion", "verification", "alignment", "downstream_verification"]


def status_file_paths():
    """Resolved against the current value of the module-level ROOT at call
    time (not import time), so tests can point ROOT at a tmp_path and get a
    real end-to-end run instead of mocking every os.path/open call."""
    return {
        "download_metadata": os.path.join(ROOT, "download_status.json"),
        "conversion": os.path.join(ROOT, "conversion_status.json"),
        "verification": os.path.join(ROOT, "verification_status.json"),
        "alignment": os.path.join(ROOT, "alignment_status.json"),
        "downstream_verification": os.path.join(ROOT, "downstream_verification_status.json"),
    }


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_TS_RE = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"[T ](?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:\.(?P<frac>\d+))?"
    r"(?P<tz>Z|[+-]\d{2}:?\d{2})?$"
)


def parse_ts(ts):
    """Hand-rolled ISO-8601 parse: handles 'Z' suffix, explicit +/-HH:MM
    offsets, and fractional seconds. Deliberately NOT datetime.fromisoformat -
    HTCF's login-node system python3 is 3.6.8, which doesn't have that method
    at all (added in 3.7), so using it would crash on every single timestamp
    the moment any lock file exists, silently, on the exact environment this
    script actually runs in. Regex + manual offset math works identically on
    any Python 3.x."""
    m = _TS_RE.match(ts.strip())
    if not m:
        raise ValueError(f"Unrecognized timestamp format: {ts!r}")
    frac = (m.group("frac") or "0").ljust(6, "0")[:6]
    dt = datetime(
        int(m.group("year")), int(m.group("month")), int(m.group("day")),
        int(m.group("hour")), int(m.group("minute")), int(m.group("second")),
        int(frac),
    )
    tz = m.group("tz")
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        offset = sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4]))
        dt = dt - offset  # normalize local-with-offset back to UTC
    return dt.replace(tzinfo=timezone.utc)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def effective_phase(status, study_id):
    studies = status.get("studies", {})
    if study_id in studies:
        return studies[study_id].get("phase")
    default = studies.get("_default_for_unlisted")
    return default  # may be a free-text string, not just a phase token - callers handle that


def _has_real_output(processed_dir):
    """True if processed/ has an actual converted artifact, not just a
    housekeeping doc. A study legitimately 'blocked' can still have a
    CONVERSION_BLOCKED.md flag file sitting in processed/ (e.g.
    Lall2025_CellStemCell) - that's expected, not a sign of a stale status,
    so .md files alone don't count as real output. Anything else (.h5ad,
    .h5mu, .parquet, .tsv, or a subdirectory like qki5_as_events/) does."""
    if not os.path.isdir(processed_dir):
        return False
    for name in os.listdir(processed_dir):
        if name.startswith("."):
            continue
        if not name.endswith(".md"):
            return True
    return False


def check_converted_vs_processed(conversion_status, dataset_root):
    """Cross-check conversion_status.json's phase claims against what's
    actually in studies/<id>/processed/ on the dataset collection. Catches
    exactly the kind of stale 'converted' claim found by hand multiple times
    this session (Ho2021, Schweingruber, DivergentC9 were all marked
    converted while their processed/ was actually empty), plus the reverse -
    real output existing under a phase that says nothing has happened yet."""
    mismatches = []
    for sid, info in conversion_status.get("studies", {}).items():
        if sid == "_default_for_unlisted" or not isinstance(info, dict):
            continue
        phase = info.get("phase")
        processed_dir = os.path.join(dataset_root, "studies", sid, "processed")
        has_output = _has_real_output(processed_dir)
        if phase == "converted" and not has_output:
            mismatches.append(f"{sid}: conversion_status.json says 'converted' but processed/ has no real output (empty, missing, or only housekeeping docs)")
        elif phase in ("not_started", "blocked") and has_output:
            mismatches.append(f"{sid}: conversion_status.json says '{phase}' but processed/ already has real output - status may be stale")
    return mismatches


def check_sample_count_consistency(dataset_root):
    """Compare build_summary.json's declared n_samples per study against the
    actual row count in all_samples.tsv for that study_id - the same
    comparison that caught the Lall2025_CellStemCell 176-vs-88 stale-count
    bug during a one-time manual QC pass, now a standing check instead."""
    mismatches = []
    build_summary = load_json(os.path.join(dataset_root, "build_summary.json"), [])
    all_samples_path = os.path.join(dataset_root, "all_samples.tsv")
    if not build_summary or not os.path.exists(all_samples_path):
        return mismatches

    actual_counts = {}
    with open(all_samples_path, newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            sid = row.get("study_id")
            if sid:
                actual_counts[sid] = actual_counts.get(sid, 0) + 1

    for entry in build_summary:
        sid = entry.get("study_id")
        declared = entry.get("n_samples")
        if sid is None or declared is None:
            continue
        if entry.get("study_dir") is None and "status" in entry:
            continue  # explicitly-skipped studies (e.g. dbGaP) - not a real mismatch
        actual = actual_counts.get(sid, 0)
        if actual != declared:
            mismatches.append(f"{sid}: build_summary.json says n_samples={declared} but all_samples.tsv has {actual} rows for this study_id")
    return mismatches


def main():
    status_files = status_file_paths()
    changelog_path = os.path.join(ROOT, "CHANGELOG.jsonl")
    checkpoint_path = os.path.join(ROOT, "checkpoints", "orchestrator.txt")
    state_path = os.path.join(ROOT, "orchestrator_state.json")
    report_path = os.path.join(ROOT, "ORCHESTRATOR_REPORT.md")

    if os.path.exists(changelog_path):
        with open(changelog_path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
    else:
        lines = []

    checkpoint = 0
    if os.path.exists(checkpoint_path):
        with open(checkpoint_path) as f:
            checkpoint = int(f.read().strip() or 0)

    # A single truncated/hand-edited line must not permanently brick every
    # future run (checkpoint only ever advances forward, so a crash here
    # would re-hit the same bad line on every subsequent run forever).
    new_events, unparseable_lines = [], 0
    for l in lines[checkpoint:]:
        try:
            new_events.append(json.loads(l))
        except json.JSONDecodeError:
            unparseable_lines += 1

    statuses = {r: load_json(status_files[r], {"studies": {}}) for r in ROLES}
    prev_state = load_json(state_path, {"streaks": {}, "last_updated_at": {}})
    # explicit per-role default so a role missing from a partially-written
    # state file (e.g. a role added after state_path was first created)
    # still starts at streak 0 instead of silently losing its counter
    prev_streaks = prev_state.get("streaks", {})
    streaks = {r: prev_streaks.get(r, 0) for r in ROLES}
    last_updated_at = prev_state.get("last_updated_at", {})

    session_health = {}
    for r in ROLES:
        updated_at = statuses[r].get("updated_at", SEED_TS)
        if updated_at == SEED_TS:
            session_health[r] = ("never_briefed", updated_at)
            streaks[r] = 0
        elif last_updated_at.get(r) == updated_at:
            streaks[r] = streaks.get(r, 0) + 1
            status_word = "possibly_stalled" if streaks[r] >= STALE_STREAK_THRESHOLD else "active"
            session_health[r] = (status_word, updated_at)
        else:
            streaks[r] = 0
            session_health[r] = ("active", updated_at)
        last_updated_at[r] = updated_at

    # stale locks - a single hand-edited/malformed 'since' value must not
    # crash the whole check run; report it as unparseable and move on.
    stale_locks, unparseable_locks = [], []
    for lock_file in glob.glob(os.path.join(ROOT, "locks", "*.json")):
        lock = load_json(lock_file, {})
        since = lock.get("since")
        if not since:
            continue
        try:
            age_hours = (datetime.now(timezone.utc) - parse_ts(since)).total_seconds() / 3600
        except ValueError:
            unparseable_locks.append((os.path.basename(lock_file), since))
            continue
        if age_hours > STALE_LOCK_HOURS:
            stale_locks.append((os.path.basename(lock_file), lock.get("held_by"), round(age_hours, 1), lock.get("note")))

    # phase contradictions - only compare against EXPLICIT per-study entries.
    # download_metadata's "_default_for_unlisted" is free text for whatever
    # studies its owner hasn't itemized yet, not a structured phase claim -
    # treating it as authoritative "not downloaded" produced a false positive
    # for every already-converted study the very first time this ran.
    contradictions = []
    dl_studies = statuses["download_metadata"].get("studies", {})
    conv_studies = statuses["conversion"].get("studies", {})
    all_study_ids = set(conv_studies.keys()) | set(statuses["downstream_verification"].get("studies", {}).keys()) | set(dl_studies.keys())
    for sid in sorted(all_study_ids):
        if sid == "_default_for_unlisted":
            continue
        conv = effective_phase(statuses["conversion"], sid)
        ver = effective_phase(statuses["downstream_verification"], sid)
        if conv == "converted" and sid in dl_studies:
            dl_phase = dl_studies[sid].get("phase")
            if dl_phase not in ("downloaded", "metadata_normalized"):
                contradictions.append(f"{sid}: conversion=converted but download_metadata explicitly reports phase='{dl_phase}'")
        if ver == "verify_failed" and conv in ("converted", "converting"):
            contradictions.append(f"{sid}: downstream_verification=verify_failed but conversion={conv}")

    # blockers worth resurfacing ('_default_for_unlisted' entries are free
    # text, not a per-study dict - skip anything that isn't a dict at all)
    blockers = [
        f"{sid}: {info.get('blocked_reason', info.get('note', ''))}"
        for sid, info in statuses["conversion"].get("studies", {}).items()
        if isinstance(info, dict) and info.get("phase") == "blocked"
    ]

    # cross-file consistency (Tier 1: cheap, local-file-only checks against
    # the actual dataset collection, not just coordination state)
    conv_mismatches = check_converted_vs_processed(statuses["conversion"], DATASET_ROOT)
    count_mismatches = check_sample_count_consistency(DATASET_ROOT)

    # --- write report ---
    ts = now_iso()
    report = [f"# ALS pipeline orchestrator report", f"Generated: {ts}", ""]

    report.append(f"## New activity since last check ({len(new_events)} events)")
    if new_events:
        for e in new_events[-30:]:  # cap so the report doesn't grow unbounded
            report.append(f"- `{e.get('ts')}` **{e.get('session')}** {e.get('action')} "
                           f"({e.get('study_id') or 'collection-wide'}): {e.get('note', '')}")
        if len(new_events) > 30:
            report.append(f"- ...and {len(new_events) - 30} more (see CHANGELOG.jsonl)")
    else:
        report.append("- none")
    report.append("")

    report.append("## Session health")
    for r in ROLES:
        status_word, updated_at = session_health[r]
        report.append(f"- **{r}**: {status_word} (status file last updated {updated_at})")
    report.append("")

    report.append("## Flags")
    any_flag = False
    if stale_locks:
        any_flag = True
        report.append(f"- **Stale locks** (held > {STALE_LOCK_HOURS}h, may be forgotten):")
        for name, held_by, age, note in stale_locks:
            report.append(f"  - `{name}` held by {held_by}, {age}h old: {note}")
    if contradictions:
        any_flag = True
        report.append("- **Cross-session phase contradictions:**")
        for c in contradictions:
            report.append(f"  - {c}")
    if any(sh[0] == "possibly_stalled" for sh in session_health.values()):
        any_flag = True
        report.append("- **Possibly stalled sessions:**")
        for r in ROLES:
            if session_health[r][0] == "possibly_stalled":
                report.append(f"  - {r}'s status file hasn't moved in >={STALE_STREAK_THRESHOLD} checks - "
                               f"may be idle, blocked, or not running.")
    if unparseable_lines:
        any_flag = True
        report.append(f"- **{unparseable_lines} malformed line(s) in CHANGELOG.jsonl** were skipped (not crashed on) - worth a manual look.")
    if unparseable_locks:
        any_flag = True
        report.append("- **Locks with an unparseable `since` field** (skipped, not staleness-checked):")
        for name, since in unparseable_locks:
            report.append(f"  - `{name}`: {since!r}")
    if conv_mismatches:
        any_flag = True
        report.append("- **Conversion status vs. actual processed/ contents mismatch:**")
        for m in conv_mismatches:
            report.append(f"  - {m}")
    if count_mismatches:
        any_flag = True
        report.append("- **Sample count mismatch (build_summary.json vs. all_samples.tsv):**")
        for m in count_mismatches:
            report.append(f"  - {m}")
    if not any_flag:
        report.append("- none")
    report.append("")

    if blockers:
        report.append("## Open blockers needing a user decision")
        for b in blockers:
            report.append(f"- {b}")
        report.append("")

    with open(report_path, "w") as f:
        f.write("\n".join(report) + "\n")

    with open(state_path, "w") as f:
        json.dump({"streaks": streaks, "last_updated_at": last_updated_at}, f, indent=2)

    # Single consistent total across every flag category - this previously
    # only summed stale_locks + contradictions even before today's additions,
    # silently undercounting relative to what the Flags section actually
    # listed (unparseable lines/locks, stalled sessions were never counted).
    total_flags = (len(stale_locks) + len(contradictions) + len(unparseable_locks)
                   + len(conv_mismatches) + len(count_mismatches)
                   + (1 if unparseable_lines else 0)
                   + sum(1 for sh in session_health.values() if sh[0] == "possibly_stalled"))

    with open(changelog_path, "a") as f:
        f.write(json.dumps({
            "ts": ts, "session": "orchestrator", "action": "check_completed", "study_id": None,
            "note": f"{len(new_events)} new events reviewed, {total_flags} flags raised.",
        }) + "\n")

    # +1 accounts for the orchestrator's own check_completed line just
    # appended above - otherwise every future run would see that line as
    # "new" and the event count would be permanently inflated by 1 forever.
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    with open(checkpoint_path, "w") as f:
        f.write(str(len(lines) + 1))

    print(f"orchestrator_check: {len(new_events)} new events, "
          f"{total_flags} flags. Report written to {report_path}")


if __name__ == "__main__":
    main()
