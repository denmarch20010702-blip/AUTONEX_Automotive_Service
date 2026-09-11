from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "postgresql+asyncpg://station:station@localhost:5432/station"
    station_login: str = "mechanic"
    station_password: str = "change-me"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-5"


settings = Settings()
