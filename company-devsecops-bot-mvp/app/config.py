from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "dev"
    app_port: int = 8080
    app_host: str = "0.0.0.0"
    app_db_path: str = "./data/mvp.db"

    model_router_default: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"

    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment: str = "gpt-5-mini"
    azure_openai_api_version: str = "2024-12-01-preview"

    gitlab_base_url: str = ""
    gitlab_token: str = ""

    require_approval_for_deploy: bool = True
    allowed_deploy_envs: str = "dev,stage,prod"

    ms_teams_bot_enabled: bool = True
    ms_teams_app_id: str = ""
    ms_teams_app_password: str = ""

    # Comma-separated user IDs or names for MVP authZ.
    authz_scan_allow: str = "*"
    authz_deploy_allow: str = "ops,sec-lead"
    authz_approve_allow: str = "sec-lead"
    authz_prod_approvers: str = "sec-lead"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
