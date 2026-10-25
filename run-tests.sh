#!/usr/bin/env bash
#
# Run the tests against a clean, disposable fixture: stop containers -> reset the fixture DB ->
# build & start -> pytest -> stop -> reset (EXIT trap, so it also runs when a test fails).
# The reset runs with Trilium stopped: overwriting document.db while SQLite has it open corrupts it.
# Extra arguments go to pytest.
set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

reset_db() {
  # Trilium's entrypoint chowns its data dir; hand it back when we're not root (CI runner).
  if [ -n "$(find fixture/trilium-data ! -user "$(id -u)" -print -quit)" ]; then
    docker compose run --rm --no-deps --user root --entrypoint chown trilium \
      -R "$(id -u):$(id -g)" /home/node/trilium-data
  fi
  git checkout -- fixture/trilium-data/
  # A killed run leaves SQLite's WAL next to the restored DB, and Trilium would replay it on start.
  # They're ignored files, so git clean wouldn't remove them.
  rm -f fixture/trilium-data/document.db-wal fixture/trilium-data/document.db-shm
}

cleanup() {
  echo "== Teardown: stopping containers and resetting DB =="
  docker compose stop
  reset_db
}
trap cleanup EXIT

docker compose stop
reset_db
docker compose up -d --build --wait --wait-timeout 300
uv run pytest "$@"
