# Market data update repair

Baseline: d0ae972bcc9a21230b23e5f3d67251d7a2a5ab6a, failed run 38910763301.

Daily date keys now accept YYYYMMDD (including integer calendar keys), YYYY-MM-DD,
and native date/datetime values at naive midnight. Missing, impossible, ambiguous,
timezone-aware and intraday values raise with row examples, before any row filtering.
The output is datetime64[ns]; date values are unchanged.

Provider results are validated separately before acceptance, so malformed/short or
extreme-return data can trigger the other provider. Each symbol uses one complete
provider history; adjusted histories are not spliced across vendors. QFQ/HFQ formulas
remain unchanged. Adjustment-factor dates use the same parser, and factors must be
positive and finite with one-to-one coverage. Missing factors remain a hard provider
failure; no unadjusted-price substitution is introduced. ETFs cannot fall back to
index endpoints.

Any configured symbol failure aborts publication and writes data_failures.csv.
Existing in-range symbol/date keys must remain present in a replacement snapshot.
Writing the parquet uses a temporary sibling and atomic replacement. The workflow
runs tests before downloading and uploads failure logs. Schedule remains weekdays
09:00 UTC / 17:00 Asia/Shanghai.

Validation:
    python -m pip install -r requirements.txt
    python -m pytest -q
    python scripts/verify_cleaning_equivalence.py

The equivalence command compares tracked prices, keys, factors, NAV, weights and
turnover against the baseline cleaner. It normalizes the old date dtype from us to
ns for comparison, explicitly checking all values.

Limits: these checks cannot prove vendor adjustment correctness or freshness.
An unchanged stale snapshot can pass, as can new gaps absent from the prior snapshot.
Do not infer current-day completeness from workflow success alone. A verified
exchange calendar plus per-symbol listing/suspension metadata is needed for a strict
freshness/new-gap gate; do not invent trading days from weekdays (Chinese holidays
and cross-border ETF calendars differ). Existing turnover imputation and backtest
missing-return conventions are unchanged. No blind retry loop or cached-data
success substitution is added. Connection failures can still cause a legitimate
failed update, preserving the last validated snapshot.

To validate the repaired live pipeline after merging:
    gh workflow run update-data.yml --ref main
    gh run list --workflow update-data.yml --limit 5
    gh run view <NEW_RUN_ID> --log-failed

Re-running the old failed run uses the old commit and does not test this fix.
Live provider access and TUSHARE_TOKEN are required. A local test pass is not
evidence that scheduled updates have resumed.

## Verified publication after transient push failures

Run 40719582828 completed the pipeline but its one-shot push failed with HTTP 408.
Publication now uses `scripts/publish_market_data.py`: three attempts, 10/20-second
backoff, and a 120-second limit per Git command. Before each push and after every
push result (including a timeout), it fetches the remote and checks commit ancestry.
Success requires the remote to contain the generated commit, even if the client
reported success. A remote descendant also counts as published. Unverifiable
remote state never authorizes another push without a fresh successful check.

Pushes are ordinary fast-forwards. Independently advanced remote history causes a
failure; rerun the workflow from the latest branch head. No force push, automatic
rebase, stash, or reset is used. Runs on the same branch are serialized without
cancelling an active run; checkout resolves the branch when the queued job starts.
Only the original generated-output allowlist is staged. Runtime `config.yaml`
changes are excluded, and unexpected pre-staged changes cause an explicit failure.

On failure, the workflow uploads generated files, pipeline diagnostics, and (when
a publication commit was created) `publication.json` and a binary
`publication.patch`, retained for 14 days. These contain the base, commit and branch
needed to inspect the remote before recovery. The patch excludes runtime config.
On a clean checkout of the recorded base, `git apply --check publication.patch`
can validate recovery before applying it. Prefer a fresh workflow run when the
remote has advanced; do not blindly apply an older market snapshot over newer data.

The publication regression tests use local bare remotes and injected transport
failures, covering transient/permanent failure, accepted-but-reported-failed pushes,
timeouts, unknown remote state, remote descendants, concurrent updates before and
during push, dirty config, unchanged outputs, and binary recovery patches.
