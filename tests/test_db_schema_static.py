"""Tests estáticos de estructura de BD — 100% offline, sin conexión real.

Parsean migrations/schema.sql y migrations/migrations.sql como texto para verificar
que todas las tablas, columnas, constraints y la consistencia Pydantic↔esquema
están en orden. No requieren Postgres ni credenciales.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"
SCHEMA_SQL = (MIGRATIONS_DIR / "schema.sql").read_text()
MIGRATIONS_SQL = (MIGRATIONS_DIR / "migrations.sql").read_text()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _tables_in(sql: str) -> set[str]:
    return {m.lower() for m in re.findall(r"CREATE TABLE\s+(\w+)", sql, re.IGNORECASE)}


def _columns_in(sql: str, table: str) -> set[str]:
    """Extrae nombres de columnas del bloque CREATE TABLE de la tabla dada."""
    pattern = rf"CREATE TABLE\s+{re.escape(table)}\s*\((.*?)\);"
    match = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
    if not match:
        return set()
    block = match.group(1)
    cols = set()
    for line in block.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY", "UNIQUE", "CHECK", "REFERENCES", "CONSTRAINT", "INDEX")):
            continue
        col_name = line.split()[0].strip('"').lower()
        if col_name:
            cols.add(col_name)
    return cols


# ─── Tablas canónicas ─────────────────────────────────────────────────────────

CANONICAL_TABLES = {
    "users",
    "species",
    "species_care_profiles",
    "species_ai_content",
    "species_common_names",
    "botanical_chunks",
    "plants",
    "sensors",
    "events",
    "friendships",
    "monthly_metrics",
}


@pytest.mark.parametrize("table", sorted(CANONICAL_TABLES))
def test_schema_contains_table(table: str):
    assert table in _tables_in(SCHEMA_SQL), f"Tabla '{table}' no encontrada en schema.sql"


# ─── Extensiones ──────────────────────────────────────────────────────────────

def test_schema_enables_pgcrypto():
    assert "pgcrypto" in SCHEMA_SQL.lower()


def test_schema_enables_vector():
    assert "create extension" in SCHEMA_SQL.lower() and "vector" in SCHEMA_SQL.lower()


# ─── pgvector ─────────────────────────────────────────────────────────────────

def test_schema_has_vector_column():
    assert "vector(1536)" in SCHEMA_SQL


def test_schema_has_match_botanical_chunks_rpc():
    assert "match_botanical_chunks" in SCHEMA_SQL


def test_schema_rpc_returns_similarity():
    assert "similarity" in SCHEMA_SQL


# ─── Columnas clave por tabla ─────────────────────────────────────────────────

@pytest.mark.parametrize("col", ["user_id", "username", "email", "created_at"])
def test_users_columns(col):
    assert col in _columns_in(SCHEMA_SQL, "users"), f"users.{col} no encontrado"


@pytest.mark.parametrize("col", [
    "id", "scientific_name", "common_name", "family", "genus",
    "gbif_taxon_key", "inaturalist_id", "source_provider",
])
def test_species_columns(col):
    assert col in _columns_in(SCHEMA_SQL, "species"), f"species.{col} no encontrado"


@pytest.mark.parametrize("col", [
    "id", "species_id",
    "min_temp_c", "max_temp_c",
    "min_light_lux", "max_light_lux",
    "min_air_humidity_pct", "max_air_humidity_pct",
    "min_soil_humidity_pct", "max_soil_humidity_pct",
    "care_data_source", "proposal_confidence", "needs_review",
    "weight_light", "weight_soil_humidity", "weight_air_humidity", "weight_temperature",
    "sensitivity_light", "sensitivity_soil_humidity", "sensitivity_air_humidity", "sensitivity_temperature",
])
def test_species_care_profiles_columns(col):
    assert col in _columns_in(SCHEMA_SQL, "species_care_profiles"), \
        f"species_care_profiles.{col} no encontrado"


@pytest.mark.parametrize("col", [
    "id", "species_id", "ai_personality_prompt", "care_summary",
    "care_tips", "fun_facts", "faq", "language", "llm_model", "generated_at",
])
def test_species_ai_content_columns(col):
    assert col in _columns_in(SCHEMA_SQL, "species_ai_content"), \
        f"species_ai_content.{col} no encontrado"


@pytest.mark.parametrize("col", ["plant_id", "user_id", "species_id", "nickname",
                                   "health_status", "health_score", "photo_storage_path"])
def test_plants_columns(col):
    assert col in _columns_in(SCHEMA_SQL, "plants"), f"plants.{col} no encontrado"


@pytest.mark.parametrize("col", ["id", "plant_id", "month", "year",
                                   "avg_temperature", "avg_soil_humidity",
                                   "avg_air_humidity", "avg_light",
                                   "avg_health_score", "health_status_majority"])
def test_monthly_metrics_columns(col):
    assert col in _columns_in(SCHEMA_SQL, "monthly_metrics"), \
        f"monthly_metrics.{col} no encontrado"


# ─── CHECK constraints ────────────────────────────────────────────────────────

def test_health_status_check_values():
    assert "'healthy'" in SCHEMA_SQL and "'warning'" in SCHEMA_SQL and "'critical'" in SCHEMA_SQL


def test_proposal_confidence_check_values():
    assert "'high'" in SCHEMA_SQL and "'medium'" in SCHEMA_SQL and "'low'" in SCHEMA_SQL


def test_friendships_status_check_values():
    assert "'pending'" in SCHEMA_SQL and "'accepted'" in SCHEMA_SQL and "'blocked'" in SCHEMA_SQL


def test_events_type_check_values():
    for val in ("'alert'", "'insight'", "'chat'", "'system'"):
        assert val in SCHEMA_SQL, f"events.type CHECK no contiene {val}"


def test_month_check_constraint():
    assert "BETWEEN 1 AND 12" in SCHEMA_SQL


# ─── UNIQUE constraints ───────────────────────────────────────────────────────

def test_species_scientific_name_unique():
    assert "scientific_name" in SCHEMA_SQL and "UNIQUE" in SCHEMA_SQL


def test_species_ai_content_unique_species_language():
    assert "UNIQUE (species_id, language)" in SCHEMA_SQL


def test_species_common_names_unique():
    assert "UNIQUE (species_id, name, language)" in SCHEMA_SQL


# ─── Consistencia schema.sql ↔ migrations.sql ────────────────────────────────

def test_migrations_sql_contains_care_weights_columns():
    """migration 003 debe añadir las columnas de pesos y sensibilidad."""
    for col in ("weight_light", "weight_soil_humidity", "sensitivity_light"):
        assert col in MIGRATIONS_SQL, f"migrations.sql no contiene columna {col}"


def test_migrations_sql_adds_photo_storage_path():
    """migration 002 debe añadir photo_storage_path a plants."""
    assert "photo_storage_path" in MIGRATIONS_SQL


def test_migrations_sql_adds_monthly_metrics_health():
    """migration 004 debe añadir avg_health_score y health_status_majority a monthly_metrics."""
    assert "avg_health_score" in MIGRATIONS_SQL
    assert "health_status_majority" in MIGRATIONS_SQL


def test_schema_and_migrations_agree_on_species_care_profiles_weights():
    """Ambos archivos deben referenciar las cuatro columnas de peso."""
    for col in ("weight_light", "weight_soil_humidity", "weight_air_humidity", "weight_temperature"):
        assert col in SCHEMA_SQL, f"schema.sql no tiene {col}"
        assert col in MIGRATIONS_SQL, f"migrations.sql no tiene {col}"


# ─── Consistencia Pydantic ↔ esquema ─────────────────────────────────────────

def test_species_record_fields_in_schema():
    from app.schemas.species import SpeciesRecord
    schema_cols = _columns_in(SCHEMA_SQL, "species")
    model_fields = set(SpeciesRecord.model_fields.keys())
    missing = model_fields - schema_cols
    assert not missing, f"SpeciesRecord tiene campos no presentes en species: {missing}"


def test_species_care_profile_record_fields_in_schema():
    from app.schemas.species import SpeciesCareProfileRecord
    schema_cols = _columns_in(SCHEMA_SQL, "species_care_profiles")
    model_fields = set(SpeciesCareProfileRecord.model_fields.keys())
    missing = model_fields - schema_cols
    assert not missing, \
        f"SpeciesCareProfileRecord tiene campos no presentes en species_care_profiles: {missing}"


def test_species_ai_content_record_fields_in_schema():
    from app.schemas.species import SpeciesAiContentRecord
    schema_cols = _columns_in(SCHEMA_SQL, "species_ai_content")
    model_fields = set(SpeciesAiContentRecord.model_fields.keys())
    missing = model_fields - schema_cols
    assert not missing, \
        f"SpeciesAiContentRecord tiene campos no presentes en species_ai_content: {missing}"


def test_plant_response_fields_in_schema():
    from app.schemas.plants import PlantResponse
    schema_cols = _columns_in(SCHEMA_SQL, "plants")
    model_fields = set(PlantResponse.model_fields.keys())
    missing = model_fields - schema_cols
    assert not missing, f"PlantResponse tiene campos no presentes en plants: {missing}"
