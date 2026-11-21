# Offline Coinbase spot foundation

This is the first, credential-free build milestone for a new spot research system.
It adds a self-contained replay package alongside the existing application. It
does **not** change the old trading configuration, repair its live execution path,
or make the existing bot safe to run. Every file in this change is under
`coinbase_spot/`; no existing launcher imports this package.

The sole command replays **local, explicitly supplied files**. There is no exchange
client, network fetcher, API-key argument, environment-secret discovery, live-mode
switch, Hermes service, model call, scheduler or deployment configuration. The
reference strategy is a transparent test of the pipeline, with no claimed edge.

## Run the offline example

Validated with **CPython 3.12.14 on Linux**; use Python 3.12 from the repository
root and rerun the scoped tests when changing the interpreter or filesystem.
The package uses only the Python standard library; installing the legacy
requirements is unnecessary. Artifact publication requires a filesystem that
supports same-directory hard links and file/directory fsync.

```bash
python -S -B -m unittest discover -s coinbase_spot/tests -p 'test_*.py' -v

python -S -B -m coinbase_spot replay \
  --manifest coinbase_spot/fixtures/synthetic_manifest.json \
  --run-id synthetic-demo-001 \
  --output-root coinbase_spot/runs \
  --initial-cash 1000 \
  --fee-bps 60 \
  --slippage-bps 10
```

**Discover tests only in `coinbase_spot/tests`.** Some old root-level test scripts
load credentials or contact an exchange during import. None is used by this build.

The example's 50 candles, product limits, cash, 60-bps-per-side fee and
10-bps-per-side slippage are **invented test assumptions**. They are not a current
Coinbase quote, the account's fee tier, a historical capture or investment evidence.
The fixture is designed to exercise an entry, a gap stop and a final liquidation.

The CLI requires explicit cash, fee and slippage assumptions. It never increases
a trade to meet a product minimum. Reusing a run ID in the same output root fails
without changing the existing run. Choose a new ID for a new experiment; failed
runs are also retained. Output beneath `coinbase_spot/runs/` is ignored by Git.

## What is included

| Component | Behavior |
|---|---|
| Models | Immutable spot product, candle, intent and fill values; finite Decimal arithmetic under a fixed context; no binary floats for money |
| Data boundary | Saved Coinbase-shaped public-product and candle JSON, exact-byte SHA256 bindings, explicit provenance and complete coverage |
| Strategy | One long/flat prior-channel breakout; completed bars only; frozen ATR stop distance; no model-produced signals or tuning |
| Risk | Cost-aware stop sizing, cash/notional/product bounds, downward quantity rounding, durable entry halts |
| Ledger | SQLite transactions, quote cash, owned inventory, fee-inclusive cost basis, partial fills/exits, cash/inventory reservations, duplicate-ID handling |
| Replay | Following-open fills, adverse tick rounding, gap/intrabar stops, full-window marked equity and cost-aware benchmarks |
| Evidence | Parameters, source/runtime identifiers, copied inputs, decisions, fills, fees, equity, journal and incomplete-run records |

These are new, focused implementations of the accounting and causal-validation
requirements identified in the audit. Existing strategy, reporting and trading
files remain available for later, tested ports. Legacy package imports are avoided
because they transitively load configuration and clients. No private repository
source or frozen historical approval receipts are copied into this package.

## Accounting and state guarantees tested here

Only owned, unreserved inventory can be sold. A pending entry counts as the single
position; it reserves cash at its worst permitted entry price including fees.
Partial fills reduce that reservation, and requesting cancellation does not free
it. Cancellation is confirmed only against the journal's cumulative fill quantity.
An uncertain order retains its reservation and blocks entries.

Each fill ID books once. Repeating the same economic fill is a no-op; reusing an ID
with different contents fails. Buying moves cash into inventory and fee-inclusive
cost basis. Selling recognizes the removed proportional basis once. A final sale
removes the remaining basis exactly; it cannot recreate the original position.
One hand-calculated regression reproduces the audit's partial-exit case: **+49.89
followed by −50.09 produces −0.20**, with final equity 999.80 from 1,000.

Each database is permanently bound to one run ID, mode, product definition and
initial simulated cash. Replay and the reserved offline `paper` namespace use
separate files and reject each other's identities. There is no `live` namespace.
An exclusive file create prevents overwriting old state. Each append and its
terminal sequence/hash record commit atomically, and reads validate the complete
journal. Missing, altered or truncated journal events fail closed. These hashes
detect accidental damage; they are not protection from a party who can rewrite
both the database and its hashes, nor are they an external backup.

The ledger survives process restart. A full strategy replay intentionally **cannot
resume** an already used ledger: strategy state recovery and live reconciliation
are later milestones. A restarted accounting reader can inspect the retained
state, but the CLI requires a new run for another complete replay.

## Fixed offline risk ceilings

| Limit | Maximum in this milestone |
|---|---:|
| Planned loss at modeled stop, including both fees and adverse exit rounding/slippage | 0.25% of marked equity |
| Entry notional | 10% of marked equity |
| Daily marked-equity loss before halting new entries | 1% |
| Observed high-water drawdown before halting new entries | 3% |
| Owned or pending positions | 1 |

Policies can be tightened in code but not increased beyond these ceilings through
the supplied policy object. The CLI uses the fixed defaults. Cash including entry
fees and product maxima provide additional bounds. The planned stop exit must
also meet the product minimum, or the entry is skipped.

Daily baselines use cash plus marked inventory, not spendable quote cash. UTC
rollover occurs before the first timed event of a new day, including a fill:
prior-day fees remain in the carried baseline, while new-day fees and price gaps
count in the new day's loss. Loss halts survive restart, price recovery and
midnight. There is no automatic reset operation.

These are **offline test limits, not approved live limits or guaranteed loss
caps**. A halt blocks new entries; existing inventory continues to use its modeled
exit. A gap can exceed planned loss. If a gap makes the exit smaller than an
exchange minimum, replay halts, retains its simulated inventory and reports an
incomplete run; it does not invent a legal fill or successful completion.

## Causal data and execution contract

The public candle format supplies each bar's opening epoch. A bar becomes visible
to a decision only after `start + interval`. The channel uses previous highs/lows,
excluding the signal bar; ATR uses completed true ranges. A decision at a close
can execute at the following open, using that open and the previously frozen ATR
for price, sizing and the stop. The entry bar's later high, low and close cannot
change the earlier entry.

Replay handles an existing gap stop before a scheduled open exit, then considers
a pending entry. Any remaining inventory is checked for protection on every bar,
independent of a previous partial exit. Intrabar stop observations, or the adverse
low while inventory is still held, occur before the close mark. Intrabar timestamps
are assigned to bar end because OHLC data does not reveal exact event times. A
scheduled open sale is completed before the later low; an exited position does
not incur losses from lows reached afterward. This is a declared conservative
bar model, not reconstructed ticks. The final holding is liquidated at the final
close with costs and a distinct `end_of_data` reason.

Missing, duplicate, mixed-product, malformed, overlapping and off-grid candles
are rejected. Newest-first external API arrays may be sorted once at ingestion;
replay requires chronological data. There is no forward filling or exchange
fallback. The loader rejects unfinished recorded coverage. Tests cover future
suffix changes, entry-bar future-price changes, gap stops, scheduled exits and
protective handling of residual inventory.

## Inputs and output evidence

See `fixtures/synthetic_manifest.json` for schema version 1. It binds:

- Product ID and interval in whole seconds.
- Coverage start and exclusive end in UTC epoch seconds.
- Explicit `synthetic` or `recorded` provenance, source, description and UTC capture time.
- Relative local paths and exact-byte SHA256 digests for product and candle files.

Referenced paths must stay inside the manifest directory. Product type must be
`SPOT`, the saved status must be online, and restricted/missing trading flags are
rejected. These checks validate a **saved snapshot**; its declaration and hash do
not prove exchange origin, current availability or historical product rules.
Recorded market data and product-rule versioning still require qualification.

Successful output contains:

- `run.json`: parameters, offline policy, upstream base revision, hashes of the
  actual implementation files and interpreter information.
- `inputs/`: original manifest, exact data bytes and a portable `capture.json`.
- `ledger.sqlite` and `events.jsonl`: persistent accounting and full event evidence.
- `report.md`: readable observations and assumptions.
- `result.json`: complete summary, decisions, fills, costs, skipped entries,
  equity observations and benchmarks; atomically published last as the completion artifact.

`failure.json` denotes an incomplete run, with its existing inputs/state retained.
A run without `result.json` is incomplete even if a storage failure prevented
writing `failure.json`.
The result includes cash and buy-and-hold comparisons. Buy-and-hold invests up to
all initial cash, while strategy entries are capped at 10%; the comparison is
explicitly not exposure-matched. Drawdown is measured at **observed model marks**,
not every market tick. No per-trade annualized Sharpe or other misleading return
annualization is reported.

## Boundaries and next build gates

This is a correctness-oriented reference implementation. The ledger rebuilds its
journal for validation; large datasets need performance qualification before
operational use. Immediate full fills do not model a queue, partial market
liquidity, depth, latency or order-book impact. Fees are exact quote-currency
amounts under a declared assumption; exchange-specific commission rounding and
other fee currencies are not implemented. Delayed fills arriving after a terminal
cancel or out of chronological order require a future reconciliation design and
are rejected here.

The next gate is qualification of actual Coinbase public-data captures and more
realistic forward-paper execution. Authenticated order semantics, recovery after
ambiguous exchange responses, private WebSocket reconciliation, a bounded Hermes
research service and provider verification remain separate work. Deployment,
credentials, live orders, merging into the old runtime and automatic promotion
are not performed or enabled by this package.

Public schema references checked during implementation:

- [Coinbase public product](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product)
- [Coinbase public candles](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-candles)
- [Coinbase sandbox limitations](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/sandbox)

Upstream baseline: `122e0066537ad0697fe7df08a40b6cc9a66675d1` in `lotbones1-code/supequant`.
