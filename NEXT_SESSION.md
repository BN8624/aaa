# NEXT SESSION - 2026-06-10

## Current State

- The 429 issue was traced to the old `aiplatform ... ?key=` access path behaving like a low-quota/express path.
- The formal service-account Vertex path is now working:
  - `.env`: `VERTEX_PROJECT=ocr-project-496308`
  - `.env`: `VERTEX_LOCATION=global`
  - service account: `ocr-pj@ocr-project-496308.iam.gserviceaccount.com`
  - IAM role added: `roles/aiplatform.user`
- Verified:
  - `python client.py` succeeds with `gemini-3.5-flash`.
  - `python probe_quota.py 8 0` passed all 8 burst calls with no 429.
- One small code edit was made:
  - `client.py` self-test output changed `✓` to `[OK]` to avoid Windows cp949 `UnicodeEncodeError`.
  - Model/API call logic was not changed in that edit.

## h4_16

- `python analyze_h1b.py h4_16` was run.
- Result:
  - rows: 11
  - valid cells: 10
  - H1b: 0/10
  - replay: alive 6, reject 2, inputmismatch 2, fake 1
- Important hygiene note:
  - First `h4_16_A1` row is an old 403 infrastructure fake from before the IAM/global fix.
  - The later `h4_16_A1` through `h4_16_E2` are the valid 10-cell run.
  - Treat `h4_16` as valid only after excluding the first 403 fake A1 duplicate.
- Ambiguous/check rows in analysis:
  - old `h4_16_A1`: 403 fake, discard
  - `h4_16_C1`: `Error: Unknown AST node type: Program`, not H1b

## Data Policy

- Do not discard the whole `h4_16` round.
- Use it as: `h4_16 valid after excluding old 403 duplicate A1`.
- If automated aggregation cannot exclude duplicate A1 cleanly, run a clean `h4_17` for a no-footnote round.

## Next Action

Recommended next step:

1. If continuing data collection, run the next clean round as `h4_17`.
2. Then run:
   - `python analyze_h1b.py h4_17`
3. Compare with `h4_16` and keep tracking H1b/H1c, especially C/E-domain data contract failures.

Operational note:

- Current formal Vertex path should be used. Do not revert to the old `?key=` path unless explicitly testing low-quota behavior.
- Watch usage in Cloud Monitoring Metrics Explorer rather than relying on Agent Platform menu visibility.

## Suggested Opening Message For Next Session

Read `NEXT_SESSION.md` first. We fixed the Vertex access path: service-account OAuth + project `ocr-project-496308` + location `global` now passes `python client.py`, and `probe_quota.py 8 0` has no 429. `h4_16` analysis is done: H1b 0/10, but the first A1 row is an old 403 fake and must be excluded. Continue from `h4_17` unless you are only doing filtered analysis of `h4_16`.
