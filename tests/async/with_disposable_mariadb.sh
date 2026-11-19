#!/usr/bin/env bash
# Run a command against disposable SQL (MariaDB by default): a new container on a random
# loopback port, removed on exit. Never sources the checkout's .env.
set -euo pipefail

IMAGE="${TEST_DB_IMAGE:-mariadb:10.11}"
case "$IMAGE" in
    mariadb:10.11) PASSWORD_VARIABLE=MARIADB_ROOT_PASSWORD ;;
    mysql:8.0) PASSWORD_VARIABLE=MYSQL_ROOT_PASSWORD ;;
    *) echo "Unsupported disposable SQL image" >&2; exit 2 ;;
esac

NAME="duris-test-db-$$-$RANDOM"
PASSWORD="test-db-$$-$RANDOM"
cleanup() { docker rm -fv "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT HUP INT TERM
# The server is thrown away with its container, so it keeps its data in memory, never
# flushes a commit to disk and keeps no binary log; nothing reads named time zones, so
# their tables are not loaded. These halve its start and a full migration. Without native
# AIO it takes none of the host's fs.aio-max-nr, which a few dozen servers exhaust.
docker run -d --name "$NAME" -p 127.0.0.1::3306 -e "$PASSWORD_VARIABLE=$PASSWORD" \
    -e MARIADB_INITDB_SKIP_TZINFO=1 -e MYSQL_INITDB_SKIP_TZINFO=1 --tmpfs /var/lib/mysql \
    "$IMAGE" --skip-log-bin --innodb-flush-log-at-trx-commit=0 --innodb-doublewrite=0 \
    --innodb-use-native-aio=0 >/dev/null
mapping="$(docker port "$NAME" 3306/tcp)"
export TEST_DB_HOST=127.0.0.1 TEST_DB_PORT="${mapping##*:}" TEST_DB_USER=root
export TEST_DB_PASSWORD="$PASSWORD"
if mysql --help 2>&1 | grep -- '--ssl-mode' >/dev/null; then
    MYSQL_SSL=(--ssl-mode=DISABLED)
else
    MYSQL_SSL=(--skip-ssl)
fi
ready=0
for _ in $(seq 1 450); do
    if mysql "${MYSQL_SSL[@]}" --protocol=tcp -h 127.0.0.1 -P "$TEST_DB_PORT" -uroot -p"$PASSWORD" -e 'SELECT 1' \
        >/dev/null 2>&1; then ready=1; break; fi
    sleep 0.2
done
[[ "$ready" == 1 ]]
"$@"
