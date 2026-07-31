from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    binance_api_key: str = ""
    binance_secret_key: str = ""
    bybit_api_key: str = ""
    bybit_secret_key: str = ""

    database_url: str = "sqlite:///quantedge.db"

    max_risk_per_trade: float = 0.02
    max_daily_drawdown: float = 0.05
    max_open_positions: int = 3
    min_risk_reward_ratio: float = 2.0

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
