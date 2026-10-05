from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    app_name: str = "Navi"
    panel_width: int = 420
    panel_height: int = 560
    agent_host: str = "127.0.0.1"
    agent_port: int = 8765

    @property
    def agent_base_url(self) -> str:
        return f"http://{self.agent_host}:{self.agent_port}/api/v1"
