from app.modules.agent_runtime.todos import update_todos


def test_todo_merge_preserves_existing_items_and_updates_summary() -> None:
    todos = [{"id": "research", "content": "Research sources", "status": "in_progress"}]

    result = update_todos(
        todos,
        {
            "merge": True,
            "todos": [{"id": "draft", "content": "Draft answer", "status": "pending"}],
        },
    )

    assert result["status"] == "ok"
    assert [item["id"] for item in todos] == ["research", "draft"]


def test_todo_rejects_multiple_in_progress_without_mutating_plan() -> None:
    todos = [{"id": "research", "content": "Research sources", "status": "in_progress"}]

    result = update_todos(
        todos,
        {
            "merge": True,
            "todos": [{"id": "draft", "content": "Draft answer", "status": "in_progress"}],
        },
    )

    assert result == {"status": "rejected", "code": "TODO_MULTIPLE_IN_PROGRESS"}
    assert todos == [{"id": "research", "content": "Research sources", "status": "in_progress"}]
