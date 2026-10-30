#!/bin/sh
set -eu

: "${KNOWFLOW_DEV_MIGRATOR_PASSWORD:?missing migration role password}"
: "${KNOWFLOW_DEV_APP_PASSWORD:?missing application role password}"
: "${KNOWFLOW_DEV_AI_PASSWORD:?missing AI role password}"

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=ON_ERROR_STOP=1 \
  --set=migrator_password="$KNOWFLOW_DEV_MIGRATOR_PASSWORD" \
  --set=app_password="$KNOWFLOW_DEV_APP_PASSWORD" \
  --set=ai_password="$KNOWFLOW_DEV_AI_PASSWORD" \
  --file=/tmp/20-set-role-passwords.sql
