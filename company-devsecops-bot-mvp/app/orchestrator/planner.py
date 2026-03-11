from .models import TaskPlan, TaskStep


def create_plan(goal: str) -> TaskPlan:
    # MVP planner: fixed 3-step decomposition for research+draft style goals.
    return TaskPlan(
        steps=[
            TaskStep(
                step_index=1,
                title="Collect relevant sources",
                tool_name="mock_search",
                tool_input={"query": goal, "limit": 5},
            ),
            TaskStep(
                step_index=2,
                title="Generate concise summary notes",
                tool_name="note_writer",
                tool_input={"goal": goal},
            ),
            TaskStep(
                step_index=3,
                title="Store draft output artifact",
                tool_name="file_store",
                tool_input={"filename": "draft_email.txt"},
            ),
        ]
    )
