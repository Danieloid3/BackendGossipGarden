from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWKS_URL: str
    FIREBASE_CREDENTIALS_PATH: str = "firebase_credentials.json"
    FIREBASE_CREDENTIALS_JSON: str | None = None
    FIREBASE_STORAGE_BUCKET: str = ""
    REDIS_URL: str

    MQTT_ENABLED: bool = False
    MQTT_HOST: str = ""
    MQTT_PORT: int = 8883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_SSL: bool = True
    MQTT_TOPIC: str = "plantas/+/sensores"
    MQTT_KEEPALIVE: int = 60

    # Plant identification pipeline
    PLANT_ID_API_KEY: str = ""
    PLANT_ID_BASE_URL: str = "https://plant.id/api/v3"
    PLANT_ID_DETAILS: str = "common_names,taxonomy,url,gbif_id,inaturalist_id,watering,description"
    PLANT_ID_TIMEOUT_SECONDS: float = 30.0

    IDENT_CONFIDENCE_LOW: float = 0.25
    IDENT_CONFIDENCE_HIGH: float = 0.75

    GBIF_BASE_URL: str = "https://api.gbif.org/v1"
    GBIF_TIMEOUT_SECONDS: float = 10.0

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_CHAT_MODEL: str = "gpt-4o"
    OPENAI_PERSONALITY_MODEL: str = "gpt-5.5"
    OPENAI_ECONOMIC_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT_SECONDS: float = 120.0
    OPENAI_MAX_RETRIES: int = 2
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_BASE_URL: str = "https://api.elevenlabs.io/v1"
    ELEVENLABS_DEFAULT_VOICE_ID: str = "21m00Tcm4TlvDq8ikWAM"
    ELEVENLABS_MODEL_ID: str = "eleven_multilingual_v2"
    ELEVENLABS_TIMEOUT_SECONDS: float = 30.0

    RAG_ENABLED: bool = True
    RAG_TOP_K: int = 5
    RAG_MIN_SIMILARITY: float = 0.55
    BOTANICAL_SOURCES_DIR: str = "botanical_sources"

    LLM_DEFAULT_OUTPUT_LANGUAGE: str = "es"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
