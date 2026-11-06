from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./concilia.db"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_bucket: str = "concilia-documents"
    minio_access_key: str = "local"
    minio_secret_key: str = "local_dev_password"
    jwt_secret: str = "local_test_only_change_me_at_least_32_chars"
    jwt_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"
    admin_username: str = "admin"
    admin_password: str = "local_admin_change_me"
    revisor_username: str = "revisor"
    revisor_password: str = "local_revisor_change_me"
    operador_username: str = "operador"
    operador_password: str = "local_operador_change_me"
    llm_api_key: str = ""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
