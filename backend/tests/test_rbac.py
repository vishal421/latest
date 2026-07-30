import pytest

from app.rbac import is_config_command, check_command_allowed, CONFIG_MODE_ENTRY, SAVE_CONFIG_COMMAND


@pytest.mark.parametrize("command", [
    "configure terminal", "conf t", "set system hostname foo",
    "delete address-object test", "commit", "edit rulebase",
    "no shutdown", "write memory", "copy running-config startup-config",
])
def test_is_config_command_true_for_config_keywords(command):
    assert is_config_command(command) is True


@pytest.mark.parametrize("command", [
    "show version", "show ip route", "ping 8.8.8.8", "show interfaces",
])
def test_is_config_command_false_for_read_commands(command):
    assert is_config_command(command) is False


def test_full_cli_roles_can_run_config_commands():
    check_command_allowed("config_admin", "configure terminal")
    check_command_allowed("super_admin", "commit")  # should not raise


def test_read_only_roles_blocked_from_config_commands():
    with pytest.raises(PermissionError):
        check_command_allowed("read_only_auditor", "configure terminal")
    with pytest.raises(PermissionError):
        check_command_allowed("noc_viewer", "write memory")


def test_read_only_roles_can_still_run_show_commands():
    check_command_allowed("read_only_auditor", "show version")  # should not raise


def test_config_mode_entry_and_save_commands_defined_per_vendor():
    for vendor in ("cisco_ios", "paloalto", "fortigate"):
        assert vendor in CONFIG_MODE_ENTRY
        assert vendor in SAVE_CONFIG_COMMAND
