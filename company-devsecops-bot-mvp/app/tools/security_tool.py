# MVP stub for security scan orchestrator.


async def scan_summary(project_id: str, branch: str) -> dict:
    return {
        "ok": True,
        "message": f"[MVP stub] Security scan requested for project={project_id}, branch={branch}",
        "checks": ["sast", "secret-scan", "dependency-scan", "container-scan"],
    }
