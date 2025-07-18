import json
import tempfile
from pathlib import Path
import pytest

from jsonmerge import merge
from could_you.config import _load_raw_json, _parse_from_json


def test_parse_from_json_with_disabled_tools():
    """Test parsing Config with disabled tools."""
    json_config = {
        "llm": {"provider": "boto3", "model": "test"},
        "mcpServers": {
            "test-server": {
                "command": "test-command",
                "args": ["arg1", "arg2"],
                "disabledTools": ["tool1", "tool2"],
            }
        },
    }

    config = _parse_from_json(json_config, Path("/test/root"))

    assert len(config.servers) == 1
    server = config.servers[0]
    assert server.name == "test-server"
    assert server.disabled_tools == {"tool1", "tool2"}


def test_parse_from_json_with_enabled_false():
    """Test parsing Config with server disabled."""
    json_config = {
        "llm": {"provider": "boto3", "model": "test"},
        "mcpServers": {
            "disabled-server": {"command": "test-command", "args": ["arg1"], "enabled": False}
        },
    }

    config = _parse_from_json(json_config, Path("/test/root"))

    assert len(config.servers) == 1
    server = config.servers[0]
    assert server.name == "disabled-server"
    assert server.enabled is False
    assert server.disabled_tools == set()  # Empty set when not specified


def test_parse_from_json_with_both_disabled_server_and_tools():
    """Test parsing Config with both server disabled and specific tools disabled."""
    json_config = {
        "llm": {"provider": "boto3", "model": "test"},
        "mcpServers": {
            "complex-server": {
                "command": "test-command",
                "args": ["arg1"],
                "enabled": False,
                "disabledTools": ["unwanted_tool"],
            }
        },
    }

    config = _parse_from_json(json_config, Path("/test/root"))

    assert len(config.servers) == 1
    server = config.servers[0]
    assert server.name == "complex-server"
    assert server.enabled is False
    assert server.disabled_tools == {"unwanted_tool"}


def test_config_merging_with_disabled_tools():
    """Test that jsonmerge uses the local config value for disabledTools."""
    global_config = {
        "llm": {"provider": "boto3", "model": "global-model"},
        "mcpServers": {
            "shared-server": {
                "command": "global-command",
                "args": ["global-arg"],
                "disabledTools": ["global_disabled_tool"],
            }
        },
    }

    local_config = {
        "mcpServers": {
            "shared-server": {
                "enabled": True,
                "disabledTools": ["local_disabled_tool", "another_disabled_tool"],
            }
        }
    }

    merged = merge(global_config, local_config)

    # The local disabled_tools should override the global ones
    assert "shared-server" in merged["mcpServers"]
    server_config = merged["mcpServers"]["shared-server"]
    assert server_config["enabled"] is True
    assert server_config["disabledTools"] == ["local_disabled_tool", "another_disabled_tool"]
    # Global command and args should still be present
    assert server_config["command"] == "global-command"
    assert server_config["args"] == ["global-arg"]


def test_load_raw_json_existing_file():
    """Test loading raw JSON from an existing file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        test_config = {
            "llm": {"provider": "boto3", "model": "test"},
            "mcpServers": {"test": {"command": "test", "args": []}},
        }
        json.dump(test_config, f)
        f.flush()

        result = _load_raw_json(Path(f.name))
        assert result == test_config

        # Clean up
        Path(f.name).unlink()


def test_load_raw_json_nonexistent_file():
    """Test loading raw JSON from a non-existent file returns empty dict."""
    result = _load_raw_json(Path("/nonexistent/file.json"))
    assert result == {}


def test_parse_from_json():
    """Test parsing Config from JSON data."""
    json_config = {
        "systemPrompt": "Test prompt",
        "llm": {"provider": "boto3", "model": "test"},
        "mcpServers": {"test-server": {"command": "test-command", "args": ["arg1", "arg2"]}},
        "env": {"TEST_VAR": "test_value"},
        "editor": "vim",
    }

    config = _parse_from_json(json_config, Path("/test/root"))

    assert config.prompt == "Test prompt"
    assert config.llm == {"provider": "boto3", "model": "test"}
    assert len(config.servers) == 1
    assert config.servers[0].name == "test-server"
    assert config.servers[0].command == "test-command"
    assert config.servers[0].args == ["arg1", "arg2"]
    assert config.env == {"TEST_VAR": "test_value"}
    assert config.editor == "vim"
    assert config.root == Path("/test/root")


def test_config_merging():
    """Test that jsonmerge properly merges global and local configs."""
    global_config = {
        "llm": {"provider": "boto3", "model": "global-model"},
        "mcpServers": {"global-server": {"command": "global-command", "args": ["global-arg"]}},
        "env": {"GLOBAL_VAR": "global_value", "SHARED_VAR": "global_shared"},
        "editor": "nano",
    }

    local_config = {
        "llm": {"model": "local-model", "temperature": 0.7},
        "mcpServers": {"global-server": {"enabled": True}},
        "env": {"LOCAL_VAR": "local_value", "SHARED_VAR": "local_shared"},
        "systemPrompt": "Local prompt",
    }

    merged = merge(global_config, local_config)

    # LLM should be merged with local taking priority
    assert merged["llm"]["provider"] == "boto3"  # from global
    assert merged["llm"]["model"] == "local-model"  # local overrides
    assert merged["llm"]["temperature"] == 0.7  # from local

    # MCP servers should be merged
    assert "global-server" in merged["mcpServers"]
    assert merged["mcpServers"]["global-server"]["enabled"] is True

    # Environment variables should be merged with local taking priority
    assert merged["env"]["GLOBAL_VAR"] == "global_value"
    assert merged["env"]["LOCAL_VAR"] == "local_value"
    assert merged["env"]["SHARED_VAR"] == "local_shared"  # local overrides

    # Local-only fields should be present
    assert merged["systemPrompt"] == "Local prompt"

    # Global-only fields should be present
    assert merged["editor"] == "nano"


def test_parse_from_json_missing_required_fields():
    """Test that parsing fails gracefully when required fields are missing."""
    json_config = {
        "mcpServers": {
            "invalid-server": {
                "command": "test-command"
                # Missing "args" field
            }
        }
    }

    with pytest.raises(ValueError, match="missing required keys"):
        _parse_from_json(json_config, Path("/test/root"))


def test_parse_from_json_empty_config():
    """Test parsing an empty configuration."""
    json_config = {}

    config = _parse_from_json(json_config, Path("/test/root"))

    assert config.prompt is None
    assert config.llm == {}
    assert config.servers == []
    assert config.env == {}
    assert config.editor is None
    assert config.root == Path("/test/root")
