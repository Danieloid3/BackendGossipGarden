from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWKS_URL: str
    FIREBASE_CREDENTIALS_PATH: str = "firebase_credentials.json"
    FIREBASE_CREDENTIALS_JSON: str | None = None
    REDIS_URL: str

    MQTT_ENABLED: bool = False
    MQTT_HOST: str = ""
    MQTT_PORT: int = 8883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_SSL: bool = True
    MQTT_TOPIC: str = "plantas/+/sensores"
    MQTT_KEEPALIVE: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
