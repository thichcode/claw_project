from .config import settings


def _split_allowlist(raw: str) -> list[str]:
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _is_allowed(actor: str, allowlist_raw: str) -> bool:
    allow = _split_allowlist(allowlist_raw)
    if "*" in allow:
        return True
    return actor.lower() in allow


def can_scan(actor: str) -> bool:
    return _is_allowed(actor, settings.authz_scan_allow)


def can_deploy(actor: str) -> bool:
    return _is_allowed(actor, settings.authz_deploy_allow)


def can_approve(actor: str) -> bool:
    return _is_allowed(actor, settings.authz_approve_allow)


def can_approve_prod(actor: str) -> bool:
    return _is_allowed(actor, settings.authz_prod_approvers)


def can_deploy_env(env: str) -> bool:
    allowed = [x.strip().lower() for x in settings.allowed_deploy_envs.split(",") if x.strip()]
    return env.lower() in allowed


def requires_approval(action: str) -> bool:
    if action == "deploy":
        return settings.require_approval_for_deploy
    return False
