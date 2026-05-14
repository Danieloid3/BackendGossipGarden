-- Adición de métricas de salud en reportes mensuales
ALTER TABLE monthly_metrics
ADD COLUMN IF NOT EXISTS avg_health_score FLOAT,
ADD COLUMN IF NOT EXISTS health_status_majority VARCHAR;
