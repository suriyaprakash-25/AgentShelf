#!/bin/sh
# Clone the primary once, then run as a hot-standby streaming replica (read-only).
set -e
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  until pg_isready -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB"; do sleep 1; done
  export PGPASSWORD="$REPLICATION_PASSWORD"
  until pg_basebackup -h db -U replicator -D "$PGDATA" -R -X stream -P; do
    rm -rf "${PGDATA:?}"/*; sleep 2
  done
  chmod 0700 "$PGDATA"
  chown -R postgres:postgres "$PGDATA"
fi
# Official images ship gosu (newer) or su-exec (older) to drop root privileges.
# A hot standby needs max_connections >= the primary's (200 in docker-compose.yml).
exec "$(command -v gosu || command -v su-exec)" postgres postgres -c hot_standby=on -c max_connections=200
