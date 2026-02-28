# MVP stub: replace with kubernetes client + RBAC service account.


async def deploy_service(service: str, env: str, image_tag: str) -> dict:
    return {
        "ok": True,
        "message": f"[MVP stub] Deploy requested: service={service}, env={env}, image={image_tag}",
    }
