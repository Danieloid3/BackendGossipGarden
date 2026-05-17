"""Tests de estructura de BD viva — requieren Postgres efímero con pgvector.

Marcados con @pytest.mark.dbschema. Solo corren en el job db-schema del CI
(o localmente si DATABASE_URL y MIGRATIONS_DATABASE_URL están configuradas).
Se saltean automáticamente si las variables de entorno no están disponibles.

El job CI crea dos BDs desechables:
  - gg_schema:     schema.sql aplicado en limpio
  - gg_migrations: legacy_schema.sql + migrations.sql aplicados en secuencia
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.dbschema

# ─── Fixtures de conexión ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def schema_conn():
    """Conexión a la BD donde se aplicó schema.sql."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL no configurada — skip de tests dbschema")
    try:
        import psycopg
        conn = psycopg.connect(url, autocommit=False)
        yield conn
        conn.close()
    except Exception as exc:
        pytest.skip(f"No se pudo conectar a DATABASE_URL: {exc}")


@pytest.fixture(scope="module")
def migrations_conn():
    """Conexión a la BD donde se aplicó legacy_schema + migrations.sql."""
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        pytest.skip("MIGRATIONS_DATABASE_URL no configurada — skip de tests dbschema")
    try:
        import psycopg
        conn = psycopg.connect(url, autocommit=False)
        yield conn
        conn.close()
    except Exception as exc:
        pytest.skip(f"No se pudo conectar a MIGRATIONS_DATABASE_URL: {exc}")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_tables(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        return {row[0] for row in cur.fetchall()}


def _get_columns(conn, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s",
            (table,),
        )
        return {row[0] for row in cur.fetchall()}


def _get_check_constraints(conn, table: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT check_clause FROM information_schema.check_constraints cc "
            "JOIN information_schema.table_constraints tc "
            "  ON cc.constraint_name = tc.constraint_name "
            "WHERE tc.table_name = %s AND tc.constraint_type = 'CHECK'",
            (table,),
        )
        return [row[0] for row in cur.fetchall()]


# ─── Tests sobre schema.sql ───────────────────────────────────────────────────

EXPECTED_TABLES = {
    "users", "species", "species_care_profiles", "species_ai_content",
    "species_common_names", "botanical_chunks", "plants", "sensors",
    "events", "friendships", "monthly_metrics",
}


@pytest.mark.parametrize("table", sorted(EXPECTED_TABLES))
def test_table_exists_in_schema_db(schema_conn, table):
    assert table in _get_tables(schema_conn), f"Tabla '{table}' no existe en la BD"


def test_vector_extension_installed(schema_conn):
    with schema_conn.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        assert cur.fetchone() is not None, "Extensión 'vector' no está instalada"


def test_botanical_chunks_has_vector_column(schema_conn):
    cols = _get_columns(schema_conn, "botanical_chunks")
    assert "embedding" in cols


def test_hnsw_index_exists(schema_conn):
    with schema_conn.cursor() as cur:
        cur.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'botanical_chunks' AND indexname = 'idx_botanical_chunks_embedding'"
        )
        assert cur.fetchone() is not None, "Índice HNSW no encontrado"


def test_match_botanical_chunks_rpc_exists(schema_conn):
    with schema_conn.cursor() as cur:
        cur.execute(
            "SELECT proname FROM pg_proc WHERE proname = 'match_botanical_chunks'"
        )
        assert cur.fetchone() is not None, "RPC match_botanical_chunks no encontrada"


@pytest.mark.parametrize("col", [
    "weight_light", "weight_soil_humidity", "weight_air_humidity", "weight_temperature",
    "sensitivity_light", "sensitivity_soil_humidity", "sensitivity_air_humidity", "sensitivity_temperature",
])
def test_care_profile_has_weights_and_sensitivity(schema_conn, col):
    cols = _get_columns(schema_conn, "species_care_profiles")
    assert col in cols, f"species_care_profiles.{col} no existe en la BD"


def test_plants_has_photo_storage_path(schema_conn):
    assert "photo_storage_path" in _get_columns(schema_conn, "plants")


def test_monthly_metrics_has_health_columns(schema_conn):
    cols = _get_columns(schema_conn, "monthly_metrics")
    assert "avg_health_score" in cols
    assert "health_status_majority" in cols


def test_health_status_check_enforced(schema_conn):
    """Inserta un health_status inválido y verifica que la BD lo rechaza."""
    import psycopg
    with schema_conn.cursor() as cur:
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO users(username, email) VALUES ('u','u@test.com') "
                "ON CONFLICT DO NOTHING"
            )
            cur.execute(
                "INSERT INTO species(scientific_name) VALUES ('Test species') "
                "ON CONFLICT DO NOTHING"
            )
            cur.execute(
                "INSERT INTO plants(user_id, species_id, nickname, health_status) "
                "SELECT user_id, id, 'p', 'invalido' FROM users u, species s LIMIT 1"
            )
        schema_conn.rollback()


# ─── Tests sobre migration path (legacy → nuevo) ─────────────────────────────

def test_migrations_creates_new_species_table(migrations_conn):
    assert "species" in _get_tables(migrations_conn)


def test_migrations_creates_species_legacy_backup(migrations_conn):
    """migrations.sql renombra species original como species_legacy."""
    assert "species_legacy" in _get_tables(migrations_conn), \
        "species_legacy no existe — migration 001 no se aplicó correctamente"


def test_migrations_creates_species_care_profiles(migrations_conn):
    assert "species_care_profiles" in _get_tables(migrations_conn)


def test_migrations_creates_botanical_chunks(migrations_conn):
    assert "botanical_chunks" in _get_tables(migrations_conn)


def test_migrations_adds_photo_storage_path(migrations_conn):
    """migration 002 añade photo_storage_path a plants."""
    assert "photo_storage_path" in _get_columns(migrations_conn, "plants")


def test_migrations_adds_care_weights(migrations_conn):
    """migration 003 añade pesos y sensibilidad a species_care_profiles."""
    cols = _get_columns(migrations_conn, "species_care_profiles")
    for col in ("weight_light", "weight_soil_humidity", "sensitivity_light"):
        assert col in cols, f"migration 003: columna {col} no encontrada"


def test_migrations_adds_health_metrics(migrations_conn):
    """migration 004 añade avg_health_score y health_status_majority a monthly_metrics."""
    cols = _get_columns(migrations_conn, "monthly_metrics")
    assert "avg_health_score" in cols
    assert "health_status_majority" in cols
