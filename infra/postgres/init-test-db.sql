-- Create the throwaway integration-test database on first boot of a fresh
-- postgres volume. backend/tests/conftest.py defaults DATABASE_URL here so
-- migration integration tests (alembic downgrade base -> upgrade head) can
-- never wipe the dev `chili` database by default.
-- NOTE: docker-entrypoint-initdb.d only runs on an EMPTY data volume; for an
-- existing stack create it once by hand:
--   docker exec chiliai-postgres-1 psql -U chili -c "CREATE DATABASE chili_test"
CREATE DATABASE chili_test OWNER chili;
