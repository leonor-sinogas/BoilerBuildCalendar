#!/usr/bin/env sh
set -eu
mkdir -p backups
docker compose exec -T db pg_dump -U clubtime_app -d clubtime | gzip > "backups/clubtime-$(date +%F-%H%M%S).sql.gz"
