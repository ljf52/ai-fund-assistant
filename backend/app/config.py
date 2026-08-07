from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI 基金助手"
    database_path: str = "data/fund_assistant.db"
    data_mode: str = "auto"
    auto_sync_enabled: bool = True
    sync_interval_minutes: int = 360
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_base_url: str = "https://api.deepseek.com"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database_file(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[1] / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
