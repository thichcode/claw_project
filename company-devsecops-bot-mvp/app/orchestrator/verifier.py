def verify_completion(steps: list[dict]) -> tuple[bool, str]:
    failed = [s for s in steps if s.get("status") == "failed"]
    if failed:
        return False, f"{len(failed)} step(s) failed"

    pending = [s for s in steps if s.get("status") != "completed"]
    if pending:
        return False, "Task still has incomplete steps"

    return True, "Task completed"
