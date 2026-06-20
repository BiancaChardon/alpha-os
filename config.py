from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    eia_api_key: str = ""
    fred_api_key: str = ""
    perplexity_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_classification_model: str = "claude-3-5-haiku-latest"
    anthropic_synthesis_model: str = "claude-sonnet-4-6"
    database_path: str = "data/alpha_os.db"
    signal_lookback_hours: int = 24
    chart_lookback_hours: int = 168
    ingestion_fixture_mode: bool = False

    @property
    def root(self) -> Path:
        return Path(__file__).resolve().parent

    @property
    def fixtures_dir(self) -> Path:
        return self.root / "tests" / "fixtures"

    @property
    def db_path(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
