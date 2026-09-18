#!/usr/bin/env sh
# Schema and application must move together.  This is deliberately an
# entrypoint (rather than a one-off README command): it also runs when the
# isolated backend_test service is invoked with pytest or alembic.
set -eu

echo "Applying database migrations..."
alembic upgrade head

exec "$@"
