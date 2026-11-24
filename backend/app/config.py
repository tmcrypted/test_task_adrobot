from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str = ""
    keitaro_base_url: str = "https://keitaro-for-tests.etolegko.com/admin_api/v1"
    campaign_prefix: str = "test_surname_"
    database_url: str = "sqlite:///./adrobot.db"
    frontend_dist: str = "../frontend/dist"


settings = Settings()
