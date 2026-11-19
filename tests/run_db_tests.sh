#!/usr/bin/env bash
# make test-db: isolated database legs and MariaDB journeys.
# Each test brings its own container, and they run side by side, longest first
# by the previous run's times. The world capture and game loop budget journeys
# measure pulse latency, so they run alone after the pool.
# Logs are kept under bin/tests/db/.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

export LOGS=bin/tests/db
TIMES=bin/tests/db-times # "name seconds" from the last run; outlives the logs
rm -rf "$LOGS"
mkdir -p "$LOGS"

# The journeys wait on the game far more than they compute, so the pool is wider
# than the machine; wider still adds load, not speed.
jobs=$(($(nproc) * 3 / 2))
jobs=${TEST_DB_JOBS:-$((jobs > 32 ? 32 : jobs))}

# As make test does: harnesses compile and link in one g++ command, which ccache
# cannot cache; scripts/mutate/g++ makes it a cached compile per source and a link.
# Coverage's g++ has to see every compile.
if [[ -z ${COVERAGE_DATA:-} ]]; then
    export PATH="$PWD/scripts/mutate:$PATH"
    export CCACHE_DIR=${CCACHE_DIR:-$PWD/bin/test-ccache}
    export CCACHE_MAXSIZE=${CCACHE_MAXSIZE:-10G} CCACHE_SLOPPINESS=${CCACHE_SLOPPINESS:-file_macro}
    export CCACHE_NOHASHDIR=${CCACHE_NOHASHDIR:-1}
fi

run_one() {
    local name=$1 started=$SECONDS
    shift
    if "$@" >"$LOGS/$name.log" 2>&1; then
        echo "PASS $name ($((SECONDS - started))s)"
    else
        echo "FAIL $name ($((SECONDS - started))s)"
        touch "$LOGS/$name.failed"
    fi
    echo "$name $((SECONDS - started))" >>"$LOGS/times"
    [[ ! -e $LOGS/$name.failed ]]
}
export -f run_one

DB=tests/async/with_disposable_mariadb.sh
# The journeys play on make build-server-fast-pulse's 125 ms pulse, twice as fast as the
# shipped 250 ms. A leg that measures the game against the wall clock runs the shipped
# server, bin/server/dms_new (REAL_SERVER_BINARY). DURIS_SERVER_BINARY runs every leg on it.
export SERVER=${DURIS_SERVER_BINARY:-bin/server/fast-pulse/dms_new}
export REAL_SERVER=${DURIS_SERVER_BINARY:-bin/server/dms_new}
started=$SECONDS

# One leg per line: its name, then its command; SERVER_BINARY is the server under test.
# Listed longest first by a measured run, the order a run without $TIMES keeps.
legs=$(cat <<EOF
newbie_regrant_warrior $DB python3 tests/async/test_mariadb_newbie_regrant_journey.py --server SERVER_BINARY Warrior
newbie_regrant_sorcerer $DB python3 tests/async/test_mariadb_newbie_regrant_journey.py --server SERVER_BINARY Sorcerer
newbie_regrant_ranger $DB python3 tests/async/test_mariadb_newbie_regrant_journey.py --server SERVER_BINARY Ranger
newbie_regrant_rogue $DB python3 tests/async/test_mariadb_newbie_regrant_journey.py --server SERVER_BINARY Rogue
castle_key_reset $DB python3 tests/async/test_castle_key_reset_journey.py --server SERVER_BINARY
flight_network $DB python3 tests/async/test_flight_network_journey.py --backend mariadb --server REAL_SERVER_BINARY
norent_key_rent $DB python3 tests/async/test_norent_key_rent_journey.py --backend mariadb --server SERVER_BINARY
locker_grant_journey $DB python3 tests/async/test_mysql_locker_grant_journey.py --server SERVER_BINARY
starter_arrow $DB python3 tests/async/test_starter_arrow_journey.py --server SERVER_BINARY
frag_cap $DB python3 tests/async/test_frag_cap_journey.py --backend mariadb --server SERVER_BINARY
legacy_traps $DB python3 tests/async/test_legacy_trap_journey.py SERVER_BINARY mariadb
artifact_owner_restart $DB python3 tests/async/test_artifact_owner_restart_journey.py --backend mariadb --server SERVER_BINARY
hatred_journey $DB python3 tests/async/run_innate_hatred_journey.py --backend mariadb --server SERVER_BINARY
death_level_projection $DB python3 tests/async/run_death_level_projection_journey.py --backend mariadb --binary SERVER_BINARY --output bin/tests/db/death-level-projection
creation_prompt $DB python3 tests/async/test_creation_prompt_journey.py --server SERVER_BINARY
bard_disharmonist $DB python3 tests/async/test_bard_disharmonist_journey.py --server REAL_SERVER_BINARY
epic_task_recovery_journey $DB python3 tests/async/test_epic_task_recovery_journey.py --server SERVER_BINARY
conjurer_gameplay $DB python3 tests/async/test_conjurer_gameplay_journey.py --server SERVER_BINARY
shambler_reflection $DB python3 tests/async/test_shambler_reflection_journey.py --server SERVER_BINARY
bard_support $DB python3 tests/async/test_bard_support_journey.py --server SERVER_BINARY
connection_limit $DB python3 tests/async/test_connection_limit_journey.py --server REAL_SERVER_BINARY
game_loop_session $DB python3 tests/async/test_game_loop_session_journey.py --server SERVER_BINARY
chaos_new_character_kit $DB python3 tests/async/test_mariadb_chaos_new_character_kit.py --server SERVER_BINARY
rested_checkpoint $DB python3 tests/async/run_mysql_rested_checkpoint_journey.py --server SERVER_BINARY
kept_character_chaos_matrix $DB python3 tests/async/test_kept_character_matrix.py --backend mariadb --server SERVER_BINARY --chaos
storage_chest_crash $DB python3 tests/async/test_storage_chest_crash_journey.py --backend mariadb --server SERVER_BINARY
websocket_session_guard $DB python3 tests/async/test_websocket_session_guard_journey.py --backend mariadb --server SERVER_BINARY
shop_multi_buy $DB python3 tests/async/test_shop_multi_buy_journey.py --backend mariadb --server SERVER_BINARY
divine_boon_zone $DB python3 tests/async/test_divine_boon_zone_journey.py --backend mariadb --server SERVER_BINARY
world_recovery $DB python3 tests/async/run_world_recovery_journey.py SERVER_BINARY
nexus_journey $DB python3 tests/async/test_mysql_nexus_journey.py --server SERVER_BINARY
character_stat_choice $DB python3 tests/async/test_character_stat_choice_journey.py --server SERVER_BINARY
smith_payment_journey $DB python3 tests/async/test_mysql_smith_payment_journey.py
epic_training_journey $DB python3 tests/async/test_mysql_epic_training_journey.py --server SERVER_BINARY
issue1021_reports $DB python3 tests/async/run_issue1021_journey.py --server SERVER_BINARY
assassin_combat $DB python3 tests/async/test_assassin_combat_journey.py --server SERVER_BINARY
weapon_immunity $DB python3 tests/async/test_weapon_immunity_journey.py --server SERVER_BINARY
issue904_qol $DB python3 tests/async/run_issue904_qol_journey.py --server SERVER_BINARY
migration_runner_engines python3 tests/async/run_migration_runner_engines.py
telemetry_posthog_gameplay python3 tests/async/run_telemetry_player_journey.py --backend mariadb
kept_character_matrix $DB python3 tests/async/test_kept_character_matrix.py --backend mariadb --server SERVER_BINARY
minor_creation_instrument $DB python3 tests/async/test_minor_creation_instrument_journey.py --server SERVER_BINARY
world_restart_crash $DB python3 tests/async/run_world_restart_journey.py SERVER_BINARY crash
deletion $DB python3 tests/async/run_mysql_deletion_journey.py --server SERVER_BINARY
generated_npc_redis $DB python3 tests/async/test_generated_npc_journey.py --server SERVER_BINARY --mode redis
pet_restart $DB python3 tests/async/test_pet_restart_journey.py --server SERVER_BINARY
artifact_guild_reward_after_artifact $DB python3 tests/async/test_mysql_artifact_guild_reward_journey.py --server SERVER_BINARY --case after_artifact
artifact_guild_reward_after_history $DB python3 tests/async/test_mysql_artifact_guild_reward_journey.py --server SERVER_BINARY --case after_history
artifact_guild_reward_before_artifact $DB python3 tests/async/test_mysql_artifact_guild_reward_journey.py --server SERVER_BINARY --case before_artifact
artifact_guild_reward_npc $DB python3 tests/async/test_mysql_artifact_guild_reward_journey.py --server SERVER_BINARY --case npc
artifact_guild_reward_pvp $DB python3 tests/async/test_mysql_artifact_guild_reward_journey.py --server SERVER_BINARY --case pvp
artifact_guild_reward_shutdown $DB python3 tests/async/test_mysql_artifact_guild_reward_journey.py --server SERVER_BINARY --case shutdown
artifact_guild_reward_standard $DB python3 tests/async/test_mysql_artifact_guild_reward_journey.py --server SERVER_BINARY --case standard
playtime $DB python3 tests/async/test_mysql_playtime_journey.py --server SERVER_BINARY
auction_item_journey $DB python3 tests/async/test_mysql_auction_item_journey.py
stalled_writer tests/async/run_mysql_stalled_writer_journey.sh
coin_denominations $DB python3 tests/async/test_mysql_coin_denomination_journey.py --server SERVER_BINARY
critical_command_schema tests/async/run_critical_command_schema_mysql.sh
gmcp_control $DB python3 tests/async/test_gmcp_control_journey.py --server SERVER_BINARY
staff_poof $DB python3 tests/async/test_staff_poof_journey.py --server SERVER_BINARY
gith_monk $DB python3 tests/async/test_gith_monk_journey.py --server SERVER_BINARY
corpse_trap_restart $DB python3 tests/async/test_corpse_trap_restart_journey.py SERVER_BINARY mariadb
saved_item_allocator $DB python3 tests/async/run_saved_item_allocator_journey.py SERVER_BINARY
account_recovery $DB python3 tests/async/test_account_recovery_mysql_journey.py --server SERVER_BINARY
legacy_migration tests/async/run_legacy_migration_mysql.sh
saved_item_recovery $DB python3 tests/async/run_saved_item_recovery_journey.py SERVER_BINARY
kept_character_recovery $DB python3 tests/async/test_kept_character_recovery_journey.py --backend mariadb --server SERVER_BINARY
shaman_totems $DB python3 tests/async/test_shaman_totems.py --server SERVER_BINARY
corpse_haul_count_cap $DB python3 tests/async/run_corpse_haul_count_cap_journey.py SERVER_BINARY mariadb
auction_money_journey $DB python3 tests/async/test_mysql_auction_money_journey.py
area_coin_pickup $DB python3 tests/async/test_area_coin_pickup.py --server SERVER_BINARY
locker_restart $DB python3 tests/async/test_mariadb_locker_journey.py --server SERVER_BINARY
world_restart_midcapture $DB python3 tests/async/run_world_restart_journey.py SERVER_BINARY midcapture
last_command_journey $DB python3 tests/async/run_last_command_journey.py --server SERVER_BINARY
first_session_currency $DB python3 tests/async/test_mariadb_first_session_currency.py --server SERVER_BINARY
game_loop_queries $DB python3 tests/async/test_mysql_game_loop_queries_journey.py --server SERVER_BINARY
information_cache $DB python3 tests/async/test_information_cache_journey.py --backend mariadb --server SERVER_BINARY
kept_character_approval $DB python3 tests/async/test_kept_character_approval_journey.py --backend mariadb --server SERVER_BINARY
creation_deferred_play $DB python3 tests/async/test_creation_deferred_play_journey.py --backend mariadb --server SERVER_BINARY
world_restart_copyover $DB python3 tests/async/run_world_restart_journey.py SERVER_BINARY copyover
headbutt_feedback $DB python3 tests/async/test_headbutt_feedback_journey.py --server SERVER_BINARY
corpse_haul $DB python3 tests/async/run_corpse_haul_journey.py SERVER_BINARY
mob_gold_dial $DB python3 tests/async/test_mob_gold_dial_runtime.py --server SERVER_BINARY
auction_coin_put $DB python3 tests/async/test_mariadb_auction_coin_put_journey.py --server SERVER_BINARY
chaos_raise $DB python3 tests/async/run_chaos_raise_transient_journey.py SERVER_BINARY
kept_starter_grant $DB python3 tests/async/test_kept_starter_grant_journey.py --backend mariadb --server SERVER_BINARY
world_restart_handover $DB python3 tests/async/run_world_restart_journey.py SERVER_BINARY handover
locker_artifact $DB python3 tests/async/test_mariadb_locker_artifact_journey.py --server SERVER_BINARY
world_restart_taken $DB python3 tests/async/run_world_restart_journey.py SERVER_BINARY taken
collector_intake_journey $DB python3 tests/async/test_mariadb_collector_intake_journey.py --server SERVER_BINARY
collector_intake $DB python3 tests/async/run_mysql_collector_intake_journey.py SERVER_BINARY
mysql_combat $DB python3 tests/async/test_mysql_combat_journey.py --server SERVER_BINARY
generated_npc $DB python3 tests/async/test_generated_npc_journey.py --server SERVER_BINARY
runtime_compatibility tests/async/run_runtime_compatibility_mysql.sh
combat_journey $DB python3 tests/async/test_mariadb_combat_journey.py --server SERVER_BINARY
world_restart_clean $DB python3 tests/async/run_world_restart_journey.py SERVER_BINARY restart
full_world_boot $DB python3 tests/async/test_mariadb_full_world_boot.py --server SERVER_BINARY
idle_timeout $DB python3 tests/async/run_mysql_idle_timeout_journey.py SERVER_BINARY
auction_list $DB python3 tests/async/run_auction_list_journey.py --server SERVER_BINARY
first_find_tips $DB python3 tests/async/run_first_find_tips_journey.py --server SERVER_BINARY
kept_chaos_starter_grant $DB python3 tests/async/test_kept_starter_grant_journey.py --backend mariadb --server SERVER_BINARY --chaos --transport websocket
ranged_kill_xp $DB python3 tests/async/test_ranged_kill_xp_journey.py --server SERVER_BINARY
artifact_guild $DB tests/async/run_artifact_guild_schema_mysql.sh
lookup_name $DB python3 tests/async/run_lookup_name_journey.py --server SERVER_BINARY
combat_outcome $DB tests/async/run_combat_outcome_schema_mysql.sh
runtime_compatibility_mariadb_11_8 env RUNTIME_DB_IMAGE=mariadb:11.8 tests/async/run_runtime_compatibility_mysql.sh
world_writer_retry $DB python3 tests/async/run_world_writer_retry_journey.py SERVER_BINARY
address_retention $DB python3 tests/async/run_address_retention_journey.py SERVER_BINARY
death_restart_journey $DB python3 tests/async/test_mariadb_death_restart_journey.py --server SERVER_BINARY
player_save_claim tests/async/run_player_save_claim_mysql.sh
hardcore_death $DB python3 tests/async/run_mysql_hardcore_death_journey.py --server SERVER_BINARY
account_recovery_journey $DB python3 tests/async/test_account_recovery_journey.py --server SERVER_BINARY
world_restart_slowread $DB python3 tests/async/run_world_restart_journey.py SERVER_BINARY slowread
bank_restart $DB python3 tests/async/run_mysql_bank_restart_journey.py SERVER_BINARY
experience_trophy tests/async/run_experience_trophy_mysql.sh
hardcore_third_death $DB python3 tests/async/test_mariadb_hardcore_death_journey.py --server SERVER_BINARY
item_transfer tests/async/run_item_transfer_schema_mysql.sh
boon_reward_zone $DB tests/async/run_boon_reward_zone_schema_mysql.sh
kept_character_competition $DB python3 tests/async/test_kept_character_competition.py --backend mariadb --server SERVER_BINARY
session_audit $DB tests/async/run_session_audit_schema_mysql.sh
collector_repository tests/async/run_collector_repository_schema_mysql.sh
epic_transaction $DB tests/async/run_epic_transaction_schema_mysql.sh
pet_repository tests/async/run_pet_repository_mysql.sh
kept_character_ambiguous_commit $DB python3 tests/async/test_kept_character_ambiguous_commit.py --server SERVER_BINARY
epic_stone_transaction $DB python3 tests/async/test_epic_stone_transaction.py
player_pid_exhaustion $DB python3 tests/async/run_player_pid_exhaustion_journey.py --server SERVER_BINARY
divine_trade $DB tests/async/run_divine_trade_mysql.sh
level_cap $DB python3 tests/async/run_level_cap_mysql.py
account_bound_reward tests/async/run_account_bound_reward_schema_mysql.sh
artifact_population_repository $DB python3 tests/async/test_artifact_population_repository.py
auction_transaction $DB tests/async/run_auction_transaction_schema_mysql.sh
epic_zone_seed_mysql python3 tests/async/run_epic_zone_seed_mysql.py --image mysql:8.0
output_preferences tests/async/run_output_preferences_mysql.sh
telemetry_schema_boot $DB python3 tests/async/run_telemetry_schema_boot_journey.py --server SERVER_BINARY
statistics $DB bash tests/async/run_statistics_mysql.sh
combat_baseline_repair tests/async/run_combat_baseline_repair_mysql.sh
kept_character $DB python3 tests/async/test_kept_character_journey.py --backend mariadb --server SERVER_BINARY
ranged_cover_message $DB python3 tests/async/test_ranged_cover_message_journey.py --server SERVER_BINARY
telemetry_repository $DB python3 tests/async/test_telemetry_repository.py --sql-fixture
collector_catalog tests/async/run_collector_catalog_schema_mysql.sh
player_load_repository $DB tests/async/run_player_load_repository_mysql.sh
collector_notification tests/async/run_collector_notification_mysql.sh
epic_zone_seed_mariadb python3 tests/async/run_epic_zone_seed_mysql.py --image mariadb:11.4
boot_preflight $DB python3 tests/async/test_mariadb_boot_preflight.py --server SERVER_BINARY
studioproc_duplicate_record $DB python3 tests/async/test_studioproc_duplicate_record.py --server SERVER_BINARY
persistence_contract tests/async/run_persistence_contract_mysql.sh
guild_frags_load $DB tests/async/run_guild_frags_load_mysql.sh
account_character_identity $DB tests/async/run_account_character_identity_mysql.sh
account_character_projection $DB tests/async/run_account_character_projection_mysql.sh
character_rename_references $DB tests/async/run_character_rename_references_mysql.sh
frag_cap_repository $DB python3 tests/async/test_frag_cap_repository.py --mysql
log_hygiene $DB python3 tests/async/test_log_hygiene_journey.py --server SERVER_BINARY
lookup_dataset tests/async/run_lookup_dataset_mysql.sh
player_replacement_state tests/async/run_player_replacement_state_mysql.sh
account_locker_conversion_check tests/async/run_account_locker_conversion_check_mysql.sh
hostname_files $DB python3 tests/async/test_hostname_files_journey.py --server SERVER_BINARY
account_bank_delta tests/async/run_account_bank_delta_mysql.sh
corpse_persistence tests/async/run_corpse_persistence_schema_mysql.sh
lifecycle_archive tests/async/run_lifecycle_archive_schema_mysql.sh
personal_data_export tests/async/run_personal_data_export_schema_mysql.sh
account_erasure tests/async/run_account_erasure_schema_mysql.sh
immutable_migration_ledger tests/async/run_immutable_migration_ledger_mysql.sh
legacy_personal_locker_access_repair tests/async/run_legacy_personal_locker_access_repair_mysql.sh
divine_boon_schema tests/async/run_divine_boon_schema_mysql.sh
sql_pool_interrupt tests/async/run_sql_pool_interrupt_mysql.sh
collector_item_owner tests/async/run_collector_item_owner_schema_mysql.sh
leaderboard_scoring $DB python3 tests/async/test_leaderboard_scoring.py
epic_task_catalog $DB python3 tests/async/test_epic_task_catalog_mysql.py
private_chest_purchase $DB python3 tests/async/run_private_chest_purchase_mysql.py
artifact_mana tests/async/run_artifact_mana_mysql.sh
launcher_stop $DB python3 tests/async/run_launcher_stop_journey.py
last_command $DB python3 tests/async/test_last_command.py --mysql
telemetry_reports_mariadb python3 tests/async/run_telemetry_reports_mysql.py --image mariadb:10.11
telemetry_reports_mysql python3 tests/async/run_telemetry_reports_mysql.py --image mysql:8.0
EOF
)

# Longest first, so that a long leg does not start late and hold the run open alone;
# a leg with no time yet goes first.
touch "$TIMES"
awk 'FILENAME != "-" { seconds[$1] = $2; next } { print ($1 in seconds ? seconds[$1] : 1e9), $0 }' \
    "$TIMES" - <<<"$legs" | sort -s -k1,1gr | cut -d' ' -f2- |
    xargs -r -P "$jobs" -L 1 bash -c '
    args=("$@")
    for i in "${!args[@]}"; do
        if [[ ${args[i]} == SERVER_BINARY ]]; then
            args[i]=$SERVER
        elif [[ ${args[i]} == REAL_SERVER_BINARY ]]; then
            args[i]=$REAL_SERVER
        fi
    done
    run_one "${args[@]}"
'  _
status=$?
run_one world_capture "$DB" python3 tests/async/test_mysql_world_capture_journey.py \
    --server "$REAL_SERVER" || status=1
run_one game_loop_budget "$DB" python3 tests/async/test_mysql_game_loop_budget_journey.py \
    --server "$REAL_SERVER" || status=1
for failed in "$LOGS"/*.failed; do
    [ -e "$failed" ] || continue
    echo
    echo "--- ${failed%.failed}.log"
    tail -n 40 "${failed%.failed}.log"
done
cp "$LOGS/times" "$TIMES"
echo
echo "make test-db: $(ls "$LOGS"/*.log | wc -l) tests in $((SECONDS - started))s"
[ "$status" -eq 0 ]
