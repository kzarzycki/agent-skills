"""github-project-board-setup's project_workflows.py: the request it sends for each spec entry."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "utilities/skills/github-project-board-setup/scripts/project_workflows.py"
)
spec = importlib.util.spec_from_file_location("project_workflows", SCRIPT)
project_workflows = importlib.util.module_from_spec(spec)
# no __pycache__ in the skill folder, an untracked file in an installed skill
sys.dont_write_bytecode, before = True, sys.dont_write_bytecode
spec.loader.exec_module(project_workflows)
sys.dont_write_bytecode = before

# the shapes the workflows page and the REST field list return, trimmed to what request() reads
FIELDS = {
    "Status": {
        "id": 111,
        "options": [
            {"id": "aaa1", "name": {"raw": "Open"}},
            {"id": "bbb2", "name": {"raw": "Merged"}},
        ],
    }
}
CURRENT = [
    {
        "name": "Pull request merged",
        "number": 2,
        "triggerType": "merged",
        "contentTypes": ["PullRequest"],
        "enabled": False,
        "actions": [
            {
                "id": 900,
                "actionType": "set_field",
                "arguments": {"fieldId": 111, "fieldOptionId": "aaa1"},
            }
        ],
    }
]
DEFAULTS = [
    {
        "defaultWorkflow": {
            "name": "Auto-add to project",
            "triggerType": "query_matched",
            "contentTypes": ["Issue", "PullRequest"],
            "actions": [
                {
                    "actionType": "get_items",
                    "arguments": {"query": "is:issue,pr is:open label:bug", "repositoryId": None},
                },
                {"actionType": "add_project_item", "arguments": {"repositoryId": None}},
            ],
        }
    },
    {
        "defaultWorkflow": {
            "name": "Item reopened",
            "triggerType": "reopened",
            "contentTypes": ["Issue", "PullRequest"],
            "actions": [
                {
                    "id": 5,
                    "actionType": "set_field",
                    "arguments": {"fieldId": 111, "fieldOptionId": "bbb2"},
                }
            ],
        }
    },
]


def build(want):
    return project_workflows.request(
        want, CURRENT, DEFAULTS, FIELDS, {"example-org/example-repo": 42}.__getitem__
    )


def test_an_existing_workflow_is_put_by_number_with_its_action_ids():
    method, body = build({"name": "Pull request merged", "set": {"Status": "Merged"}})
    assert method == "PUT"
    assert body == {
        "workflowNumber": 2,
        "name": "Pull request merged",
        "contentTypes": ["PullRequest"],
        "enabled": True,
        "actions": [
            {
                "id": 900,
                "actionType": "set_field",
                "arguments": {"fieldId": 111, "fieldOptionId": "bbb2"},
            }
        ],
    }


def test_a_new_workflow_is_posted_from_the_default_with_the_query_and_repository_filled_in():
    method, body = build(
        {
            "name": "Auto-add to project",
            "query": "is:pr is:open",
            "repository": "example-org/example-repo",
        }
    )
    assert method == "POST"
    assert body["workflow"]["triggerType"] == "query_matched"
    assert body["workflow"]["actions"] == [
        {"actionType": "get_items", "arguments": {"query": "is:pr is:open", "repositoryId": 42}},
        {"actionType": "add_project_item", "arguments": {"repositoryId": 42}},
    ]
    # the page's defaults are not changed for the next entry
    assert DEFAULTS[0]["defaultWorkflow"]["actions"][0]["arguments"]["repositoryId"] is None


def test_a_new_workflow_drops_action_ids_and_takes_the_spec_content_types():
    method, body = build(
        {"name": "Item reopened", "contentTypes": ["PullRequest"], "set": {"Status": "Open"}}
    )
    assert method == "POST"
    assert body["workflow"]["contentTypes"] == ["PullRequest"]
    assert body["workflow"]["actions"] == [
        {"actionType": "set_field", "arguments": {"fieldId": 111, "fieldOptionId": "aaa1"}}
    ]


def test_enabled_false_switches_a_workflow_off():
    _, body = build({"name": "Pull request merged", "enabled": False})
    assert body["enabled"] is False


@pytest.mark.parametrize(
    "want, message",
    [
        ({"name": "Item closed"}, "no workflow named 'Item closed'"),
        ({"name": "Item reopened", "set": {"Status": "Done"}}, "Status has no option 'Done'"),
        ({"name": "Item reopened", "set": {"Priority": "P1"}}, "no field 'Priority'"),
    ],
)
def test_a_name_the_board_does_not_have_is_refused(want, message):
    with pytest.raises(ValueError, match=message):
        build(want)
