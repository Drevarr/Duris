# Memory authority cleanup: current plan

[Issue #583](https://github.com/LuminariMUD/Duris/issues/583).
Worktree: `/home/aiwithapex/projects/duris-issue-583-memory-authority-plan`.
Current branch: `branch/issue-583-final-qualification`,
[PR #604](https://github.com/LuminariMUD/Duris/pull/604).

**Status:** sequential PR review and integration are in progress. Focused native
regressions and both server builds pass; serving acceptance is being repeated on
the integrated source. Review fixes are included before their introducing PRs
merge. No release, deployment or production repair is included.

## Outcome and limits

Follow [ADR 0002](../adr/0002-persistence-reset-memory-is-the-authority.md):
live objects establish current placement; saved payloads restore unloaded objects;
durable ownership filters former holders' copies. The optional ownership cache
must not veto ordinary movement, valid artifact recovery or feeding.

Keep canonical uniqueness, pending operations, retirement, source qualification,
damaged-source retention, timer/soul rules and required economy settlement.
Keep the explicit pet-custody and durable NORENT/key-rent compatibility rules.
These real consumers still need cache bookkeeping; deleting the entire cache
would break them.

No new ownership manager, cache-sync worker, per-movement persistence, retry
service, journal, migration, revision format or force-recovery command is needed.
Do not expand this into a general cache-removal or hardening project.

## Necessary changes already implemented

These are the acceptance contract and the owning files, not another work queue.

- **Artifact admission and feeding** — `src/guild/artifact.c` and
  `src/player/player_load_items.c`: the qualifier and constructor share source,
  captured-custody and canonical checks. Live owner correction follows the actual
  canonical body's carried/worn/nested placement. Cache disagreement alone,
  including an apparently newer revision, grants no authority over that body.
  Competing bodies, pending creation, retired identities and invalid sources
  remain rejected.
- **Delayed reads** — `src/player/player_load_pipeline.c`,
  `player_save_worker.h`, `player_load_items.c`, `player_load_materialize.c`,
  `player_load_offline.c` and `src/account/account.c`: artifact loads use the
  existing writer counters to detect overlapping work. Refresh through the
  existing load queue with the original identity, callback and deadline.
  Never retain a source merely because its read is stale. Direct/boot reads
  retain their quiescent contract. Unrelated writes can also invalidate a read;
  this conservative behavior does not justify a new per-item tracking scheme.
- **Old copies and expiry** — the artifact service and item qualifier omit only
  proven obsolete/retired copies, preserving independent bag contents and
  damaged or unresolved evidence. Successful live recovery discards obsolete
  boot player locators, preserving pinned world sources and cancellation
  rollback. Offline expiry then follows the current holder.
- **Floor/copyover capture** — `src/world/world_recovery_pipeline.c` captures
  the physical tree. Copyover includes cached metadata only when it matches the
  actual room or logical corpse root. Saved-duplicate exclusion stays at restore;
  legacy marked records keep their required compatibility path.
- **Shop revisions** — `src/economy/shop_trade_transaction.c` passes its
  existing per-item committed revisions to `src/item/item_ownership_runtime.c`.
  The other caller, creation/adopted-object repair in
  `src/item/item_movement_transaction.c`, uses exact revisions where available;
  unknown memory-held batch revisions are zero, never a guessed maximum.
  Custody remains available to pet/rent consumers. Artifact sales and full-bag
  sales are prohibited gameplay and do not justify extra machinery.
- **NPC containers** — `src/mob/mobact.c` uses ordinary equipment and `put()`
  rules after loot movement, preserving capacity, artifact restrictions and traps.
  `src/world/handler.c` pet teardown and `src/player/player_snapshot_capture.c`
  rent behavior remain compatible with unknown cached revisions.
- **Diagnostics and recovery** — existing artifact logs name the failed condition
  and distinguish source, captured custody and optional cache values.
  `artifact hunt <initial>` remains read-only; staff notices remain bounded.
  Inspect, correct genuine source damage through its authorized workflow, then
  load afresh through the same qualifier. Resolve actual live/pending reservations
  before retrying; no bypass or unconditional release.

## Shortest remaining path

When implementation is explicitly resumed:

1. Review the aggregate diff from `5708e269974ab070ea224f720e7e2e787e2d6671`
   against the contract above and the proof below. Remove only task-owned
   machinery with no required behavior. Do not reimplement completed chunks.
2. Resolve specific review findings or uncovered acceptance conditions in the
   existing code and tests. Reuse passing evidence; rerun only affected checks.
   C/C++ edits require formatting and `make -C src`; shared persistence changes
   also require the flat-file build. No new harness framework or blanket burn-in.
3. Keep each resulting chunk committed, pushed and review-ready, stacking only
   actual dependencies. Update this document with the result and any remaining
   limit. Finish when the requirements are proven and the checkout/PRs are ready
   for review; do not wait for CI or add a further cleanup phase.

## Required proof and existing evidence

Acceptance still requires ordinary handoff, corpse loot, nested movement,
save/unload/repeated login and feeding to work through admission and attachment.
Also cover the former holder's stale save, handoff/save/unload during an outstanding
read, current-holder offline expiry, floor/copyover after corpse or locker pickup,
and shop sale/buyback after handoffs advance revisions. Exercise mixed revisions
at a supported multi-item boundary. Preserve UID, affects/enhancements, timer,
soul, mana, nesting and unrelated inventory on both MariaDB and flat-file paths.
Duplicate, retirement, corruption, rollback, pet lifetime/teardown and rent/key
controls must continue to hold.

Existing results are recorded below; a green test counts only for its assertions.
Do not rerun the original investigation driver: it asserts the old failures.

- **Serving, both backends:** artifact handoff, repeated login, stale tracking,
  feeding and cold restart; shop handoff/sale/buyback with exact revision advances,
  then restart preserving 108 ration UIDs, nesting and wallet. MariaDB additionally
  exercised legacy conflict cleanup, offline expiry and a fresh artifact generation.
- **Native regression suites:** `test_artifact_creation_admission.py` covers real
  canonical construction, corpse binding, nested recovery, ordinary/epic/monolith
  feeding, old-holder cleanup, expiry and delayed replies. Its threaded read uses
  a stubbed writer/storage boundary. `test_player_load_{items,pipeline,offline}.py`
  covers loading/refresh; `test_artifact_hunt_inspection.py` covers read-only
  diagnostics. Sanitizer checks passed where enabled.
- **Other native suites:** `test_world_recovery_pipeline.py` covers actual
  capture/restore codecs, stale corpse/locker/pet/room metadata, logical corpse
  roots, duplicates and rollback. `test_item_ownership_runtime.py` and
  `test_shop_trade_transaction.py` cover exact/mixed revisions.
  `test_put_trap_lifecycle.py`, `test_get_trap_lifecycle.py`,
  `test_items_move_in_memory.py` and `test_item_movement_input_queue.py` cover
  NPC/movement/trap controls.
- **Compatibility/payloads:** `test_player_snapshot_capture.py` and
  `test_pet_control_drop.py` cover unknown-revision rent/pet behavior;
  `test_pet_restart_journey.py` passed two flat-file restart cycles and finite/
  permanent-pet equipment/lifetime checks. `test_artifact_mana_game.py` covers
  mana conservation/reload. `run_player_load_repository_mysql.sh`,
  `run_player_save_claim_mysql.sh`, `test_flatfile_player_repository.py` and
  `test_flatfile_item_repository.py` cover payloads, claims, retention and rollback.

All test paths above are under `tests/async/`; run Python files with `python3`
and shell files with `bash`. Local evidence is under ignored
`bin/tests/memory-authority-583/`: `final-admission.log`,
`serving-{mariadb,flatfile}.log`, `shop-{mariadb,flatfile}-run.log`,
`shop-{mariadb,flatfile}.json`, `pet-restart.log`,
`{norent,pet}-unknown.log` and `final-{mysql-payloads,flat-payloads,mysql-save-load,flat-items,mana}.log`.
Artifact reports are `bin/analysis/artifact-owner/{mariadb,flatfile}.json`.
Earlier chunk checks and builds are recorded in the PRs. Missing local evidence
in a new checkout is not proof of failure or permission to claim a pass.

Exact build and serving commands, only when relevant work requires repeating them:

```sh
make -C src -j4
make -C src PERSISTENCE_BACKEND=flatfile BIN_ROOT="$PWD/bin/memory-authority-flat" -j4
bash tests/async/with_disposable_mariadb.sh python3 tests/async/test_artifact_owner_restart_journey.py --backend mariadb --server bin/server/dms_new
python3 tests/async/test_artifact_owner_restart_journey.py --backend flatfile --server bin/memory-authority-flat/server/dms_new
bash tests/async/with_disposable_mariadb.sh python3 tests/async/test_shop_multi_buy_journey.py --backend mariadb --server bin/server/dms_new --report bin/tests/memory-authority-583/shop-mariadb.json
python3 tests/async/test_shop_multi_buy_journey.py --backend flatfile --server bin/memory-authority-flat/server/dms_new --report bin/tests/memory-authority-583/shop-flatfile.json
TMPDIR="$PWD/bin/tests" python3 tests/async/test_pet_restart_journey.py "$PWD/bin/memory-authority-flat/server/dms_new"
```

Use disposable schemas/state and private loopback servers. Native codec coverage
does not establish a serving Redis/copyover journey; the delayed-read harness
does not establish a deliberately delayed real-database journey. Those broader
claims remain unverified. Add proof only for an acceptance condition not already
covered at its required boundary. The production incident and historical cache
fields were not re-inspected.

## Review stack

In dependency order, with details and history retained in Git/PRs:
[#589](https://github.com/LuminariMUD/Duris/pull/589) →
[#590](https://github.com/LuminariMUD/Duris/pull/590) →
[#591](https://github.com/LuminariMUD/Duris/pull/591) →
[#592](https://github.com/LuminariMUD/Duris/pull/592) →
[#593](https://github.com/LuminariMUD/Duris/pull/593) →
[#594](https://github.com/LuminariMUD/Duris/pull/594) →
[#595](https://github.com/LuminariMUD/Duris/pull/595) →
[#596](https://github.com/LuminariMUD/Duris/pull/596) →
[#597](https://github.com/LuminariMUD/Duris/pull/597) →
[#603](https://github.com/LuminariMUD/Duris/pull/603) →
[#604](https://github.com/LuminariMUD/Duris/pull/604).

History: investigated and implemented November 2, 2026; paused after qualification.
