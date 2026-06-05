# SLYK Backend — Domain-Driven App Structure

Every app under `apps/` is a self-contained **bounded context** with the same
symmetric layout. Pure logic is decoupled from side-effect-heavy orchestration,
and every domain ships an idempotent reconciliation `RecoveryManager`.

## Symmetric layout (identical in every app)

```text
apps/<domain>/
  models/            schema ONLY — no logic
  dtos.py            Pydantic DTOs for data crossing the app boundary
  utils.py           pure, stateless functions (math, formatting)  — NO model imports
  helpers.py         orchestration aids (cache keys, validators)    — NO model imports
  clients.py         external provider interfaces (normalize payloads -> DTOs)
  services.py        domain logic — the ONLY place mutations happen
  recovery.py        RecoveryManager(BaseRecoveryManager) — idempotent reconciliation
  tasks.py           @shared_task wrappers (Celery beat-scheduled)
  serializers.py     DRF transport
  views.py           transport only — delegate to services
  urls.py            router/paths
  admin.py           Django admin
```

## Import contract (enforced)

| Module | May import | Must NOT import |
|--------|-----------|-----------------|
| `utils.py` | stdlib, `common` | any `models`, Django ORM |
| `helpers.py` | stdlib, `common`, `utils` | any `models`, Django ORM |
| `services.py` | `models`, `dtos`, `utils`, `helpers`, `clients`, **other apps' `services`** | other apps' `models` |
| `recovery.py` | same as `services` | other apps' `models` (except read-only ledger checks) |
| `views`/`serializers` | `services`, `dtos`, own `models` | business logic |

**Cross-app integration is by ID + DTO, never by cross-app ForeignKey or model
import.** Money lives only in `wallet`; balance shown elsewhere is derived via
`wallet.services`.

## Idempotency model

All money movement flows through `wallet.services.post_entry`, which writes a
`LedgerEntry` keyed by a **unique `idempotency_key`** (`get_or_create`). Replays
collide on that key and become no-ops — this is what makes both live retries and
recovery safe. Keys are deterministic (e.g. `wallet:bet:42:stake`), so recovery
can recompute them without persistence.

## Per-domain recovery strategies

| Domain | Manager entry point | Detects | Idempotent repair |
|--------|---------------------|---------|-------------------|
| `wallet` | `reconcile_wallet_ledger` | cached balance drift vs ledger | sets `balance = Σ entries` (pure function of immutable ledger; never writes entries) |
| `sportsbook` | `handle_orphaned_bet_states` | bets stuck `PENDING` | promote to OPEN if stake debit exists; else drive keyed debit; else VOID |
| `casino` | `retry_casino_debit_sequence` | rounds `PENDING`, `debit_confirmed=False` | confirm if debit exists; else drive keyed debit; else VOID |
| `promotions` | `reconcile_promotion_claims` | uncredited bonuses; expired claims | keyed bonus re-credit (flag-gated); ACTIVE→EXPIRED |
| `accounts` | `RecoveryManager` (KYC) | players stuck `pending` past SLA | re-drive provider verification (forward-only transitions) |
| `livechat` | `reconcile_undelivered_messages` | messages `delivered=False` | re-publish; flag-gated one-way transition |

Each manager subclasses `common.recovery.BaseRecoveryManager`, supports
`dry_run=True` (report without mutating), and is invoked by a Celery beat task in
`apps.<domain>.tasks` (schedule in `config.settings.CELERY_BEAT_SCHEDULE`).
Re-running any manager is safe: it either finds nothing to do or repairs without
duplicating side effects.
