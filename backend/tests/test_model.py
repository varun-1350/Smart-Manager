import pytest
import json
from unittest.mock import AsyncMock, patch
from agent.model import OllamaClient, AgentStepDecision, ProposedAction


def test_proposed_action_validation():
    action = ProposedAction(
        tool="fs_list_dir",
        parameters={"path": "D:\\"},
        reasoning="Inspect directory contents",
    )
    assert action.tool == "fs_list_dir"
    assert action.parameters["path"] == "D:\\"
    assert action.reasoning == "Inspect directory contents"


def test_agent_step_decision_validation():
    decision = AgentStepDecision(
        summary="Found 1 file to open",
        actions=[
            ProposedAction(tool="fs_open_file", parameters={"path": "D:\\Cat.png"})
        ],
        is_complete=False,
    )
    assert len(decision.actions) == 1
    assert decision.actions[0].tool == "fs_open_file"
    assert decision.is_complete is False


def test_extract_json_variants():
    # Direct json
    raw1 = '{"summary": "test", "actions": [], "is_complete": true}'
    assert OllamaClient._extract_json(raw1) == raw1

    # Markdown fence
    raw2 = '```json\n{"summary": "test", "actions": [], "is_complete": true}\n```'
    extracted2 = OllamaClient._extract_json(raw2)
    assert json.loads(extracted2)["summary"] == "test"

    # Embedded in conversational prose
    raw3 = 'Here is the plan:\n{"summary": "embedded", "actions": [], "is_complete": false}\nHope this helps!'
    extracted3 = OllamaClient._extract_json(raw3)
    assert json.loads(extracted3)["summary"] == "embedded"


@pytest.mark.asyncio
async def test_generate_structured_success():
    client = OllamaClient(base_url="http://mock-ollama:11434", model="test-model")
    mock_response = json.dumps({
        "summary": "Listing downloads",
        "actions": [{"tool": "fs_list_downloads", "parameters": {"limit": 10}, "reasoning": "User requested recent downloads"}],
        "is_complete": False
    })

    with patch.object(client, "generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = f"```json\n{mock_response}\n```"
        result = await client.generate_structured(
            prompt="Find 10 most recent downloads",
            response_model=AgentStepDecision
        )
        assert isinstance(result, AgentStepDecision)
        assert result.summary == "Listing downloads"
        assert len(result.actions) == 1
        assert result.actions[0].tool == "fs_list_downloads"


@pytest.mark.asyncio
async def test_generate_structured_retry_on_malformed_then_success():
    client = OllamaClient(base_url="http://mock-ollama:11434", model="test-model")
    good_response = json.dumps({
        "summary": "Recovered plan",
        "actions": [],
        "is_complete": True,
        "final_answer": "Done"
    })

    with patch.object(client, "generate", new_callable=AsyncMock) as mock_gen:
        # First call returns non-json, second call returns valid json
        mock_gen.side_effect = [
            "I will help you with that right now without json",
            good_response
        ]
        result = await client.generate_structured(
            prompt="Help me",
            response_model=AgentStepDecision,
            retries=1
        )
        assert result.is_complete is True
        assert result.summary == "Recovered plan"
        assert mock_gen.call_count == 2
