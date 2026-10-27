from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Enrollment Reservation Management System"
    secret_key: str
    database_url: str = "postgresql+psycopg://enroll:enroll_password@db:5432/enrolldb"
    cookie_secure: bool = False
    session_max_age: int = 60 * 60 * 8  # 8 hours
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
