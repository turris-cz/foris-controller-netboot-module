#
# foris-controller-netboot-module
# Copyright (C) 2019 CZ.NIC, z.s.p.o. (http://www.nic.cz/)
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
#

import pytest
import os
import shutil
import typing
import time
import copy

from foris_controller_testtools.fixtures import (
    backend,
    infrastructure,
    start_buses,
    mosquitto_test,
    ubusd_test,
)
from foris_controller_testtools.infrastructure import Infrastructure


DEVICE_PATH = "/tmp/foris-controller-netboot-test"


def check_accept_notification(infra: Infrastructure, task_id: str, expected_state: str):
    filters = [("netboot", "accept")]
    notifications = None
    old_len: int = 0

    for i in range(1, 5):
        old_len = len(notifications or [])
        notifications = infra.get_notifications(notifications, filters)
        notification_data = [e["data"] for e in notifications[old_len:]]
        if [
            e
            for e in notification_data
            if e["task_id"] == task_id and e["status"] == expected_state
        ]:
            return
        time.sleep(0.1 * (i ** 2))

    raise Exception(f"Failed to get netboot.accept notification ({task_id}, {expected_state})")


@pytest.fixture(scope="function")
def init_netboot_devices():
    try:
        shutil.rmtree(DEVICE_PATH, ignore_errors=True)
    except Exception:
        pass

    dir_path = os.path.join(DEVICE_PATH, "0000000D300002AF")
    os.makedirs(dir_path)

    dir_path = os.path.join(DEVICE_PATH, "0000000D30000299")
    os.makedirs(dir_path)

    with open(os.path.join(dir_path, "accepted"), "w") as f:
        f.flush()

    dir_path = os.path.join(DEVICE_PATH, "0000000D3000028E")
    os.makedirs(dir_path)

    with open(os.path.join(dir_path, "transfering"), "w") as f:
        f.flush()

    yield DEVICE_PATH

    try:
        shutil.rmtree(DEVICE_PATH, ignore_errors=True)
    except Exception:
        pass


def test_list(infrastructure, start_buses, init_netboot_devices):
    res = infrastructure.process_message({"module": "netboot", "action": "list", "kind": "request"})
    assert "devices" in res["data"]
    for device in res["data"]["devices"]:
        set(device.keys()) == {"serial", "state"}


def test_revoke(infrastructure, start_buses, init_netboot_devices):
    filters = [("netboot", "revoke")]
    notifications = infrastructure.get_notifications(filters=filters)

    res = infrastructure.process_message(
        {
            "module": "netboot",
            "action": "revoke",
            "kind": "request",
            "data": {"serial": "0000000D30000299"},
        }
    )
    assert "data" in res
    assert res["data"]["result"] is True
    notifications = infrastructure.get_notifications(notifications, filters=filters)
    assert notifications[-1] == {
        "module": "netboot",
        "action": "revoke",
        "kind": "notification",
        "data": {"serial": "0000000D30000299"},
    }

    res = infrastructure.process_message(
        {
            "module": "netboot",
            "action": "revoke",
            "kind": "request",
            "data": {"serial": "0000000D30000299"},
        }
    )
    assert "data" in res
    assert res["data"]["result"] is False

    # missing
    res = infrastructure.process_message(
        {
            "module": "netboot",
            "action": "revoke",
            "kind": "request",
            "data": {"serial": "0000000D30000312"},
        }
    )
    assert "data" in res
    assert res["data"]["result"] is False

    res = infrastructure.process_message({"module": "netboot", "action": "list", "kind": "request"})
    assert {"serial": "0000000D30000299", "state": "incoming"} in res["data"]["devices"]

    # transfering
    res = infrastructure.process_message(
        {
            "module": "netboot",
            "action": "revoke",
            "kind": "request",
            "data": {"serial": "0000000D3000028E"},
        }
    )
    assert "data" in res
    assert res["data"]["result"] is False

    res = infrastructure.process_message({"module": "netboot", "action": "list", "kind": "request"})
    assert {"serial": "0000000D3000028E", "state": "transfering"} in res["data"]["devices"]


def test_accept(infrastructure, start_buses, init_netboot_devices):

    res = infrastructure.process_message(
        {
            "module": "netboot",
            "action": "accept",
            "kind": "request",
            "data": {"serial": "0000000D300002AF"},
        }
    )
    check_accept_notification(infrastructure, res["data"]["task_id"], "succeeded")

    res = infrastructure.process_message(
        {
            "module": "netboot",
            "action": "accept",
            "kind": "request",
            "data": {"serial": "0000000D300002AF"},
        }
    )
    check_accept_notification(infrastructure, res["data"]["task_id"], "failed")

    res = infrastructure.process_message(
        {
            "module": "netboot",
            "action": "accept",
            "kind": "request",
            "data": {"serial": "0000000D30000312"},
        }
    )
    check_accept_notification(infrastructure, res["data"]["task_id"], "failed")

    res = infrastructure.process_message({"module": "netboot", "action": "list", "kind": "request"})
    assert {"serial": "0000000D300002AF", "state": "accepted"} in res["data"]["devices"]

    # transfering
    res = infrastructure.process_message(
        {
            "module": "netboot",
            "action": "accept",
            "kind": "request",
            "data": {"serial": "0000000D3000028E"},
        }
    )
    check_accept_notification(infrastructure, res["data"]["task_id"], "failed")

    res = infrastructure.process_message({"module": "netboot", "action": "list", "kind": "request"})
    assert {"serial": "0000000D3000028E", "state": "transfering"} in res["data"]["devices"]


def test_commands_list(infrastructure, start_buses, init_netboot_devices):
    res = infrastructure.process_message(
        {"module": "netboot", "kind": "request", "action": "commands_list"}
    )
    assert "errors" not in res
    assert "data" in res
    assert "controllers" in res["data"]


def test_command_set(infrastructure, start_buses, init_netboot_devices):
    filters = [("netboot", "command_set")]

    infrastructure.process_message(
        {
            "module": "netboot",
            "action": "accept",
            "kind": "request",
            "data": {"serial": "0000000D30000299"},
        }
    )
    infrastructure.process_message(
        {
            "module": "netboot",
            "action": "revoke",
            "kind": "request",
            "data": {"serial": "0000000D300002AF"},
        }
    )

    def set_check(controller_id, module, action, data, result):
        notifications = infrastructure.get_notifications(filters=filters)

        command = {"module": module, "action": action}
        if data is not None:
            command["data"] = data

        res = infrastructure.process_message(
            {
                "module": "netboot",
                "kind": "request",
                "action": "command_set",
                "data": {"controller_id": controller_id, "command": command},
            }
        )

        assert res["data"]["result"] == result
        if result:
            # check notifications
            notifications = infrastructure.get_notifications(notifications, filters=filters)
            assert notifications[-1]["data"]["controller_id"] == controller_id
            assert notifications[-1]["data"]["command"]["module"] == module
            assert notifications[-1]["data"]["command"]["action"] == action
            if data:
                assert notifications[-1]["data"]["command"]["data"] == data
            else:
                assert "data" not in notifications[-1]["data"]["command"]
            assert "module_version" in notifications[-1]["data"]["command"]
            module_version = notifications[-1]["data"]["command"]["module_version"]
            assert "stored_time" in notifications[-1]["data"]["command"]
            stored_time = notifications[-1]["data"]["command"]["stored_time"]

            # check whether list
            res = infrastructure.process_message(
                {"module": "netboot", "kind": "request", "action": "commands_list"}
            )
            controllers = [
                e for e in res["data"]["controllers"] if e["controller_id"] == controller_id
            ]
            assert len(controllers) == 1
            commands = [
                e
                for e in controllers[0]["commands"]
                if e["module"] == module and e["action"] == action
            ]
            assert len(commands) == 1
            if data:
                assert commands[0]["data"] == data
            else:
                assert "data" not in commands[0]
            assert commands[0]["module_version"] == module_version
            assert commands[0]["stored_time"] == stored_time

    # controller not in netboot list
    set_check("0000000D30000312", "my_mod", "my_action", {"some": "data"}, False)

    # controller in incomming list
    set_check("0000000D300002AF", "my_mod", "my_action", {"some": "data"}, False)

    # controller in transfering list
    set_check("0000000D3000028E", "my_mod", "my_action", {"some": "data"}, False)

    # with data
    set_check("0000000D30000299", "my_mod", "my_action", {"some": "data"}, True)

    # without data
    set_check("0000000D30000299", "my_mod2", "my_action2", None, True)

    # set data
    set_check("0000000D30000299", "my_mod2", "my_action2", {"some": "data"}, True)

    # unset data
    set_check("0000000D30000299", "my_mod", "my_action", None, True)


def test_command_unset(infrastructure, start_buses, init_netboot_devices):
    filters = [("netboot", "command_unset")]

    infrastructure.process_message(
        {
            "module": "netboot",
            "action": "accept",
            "kind": "request",
            "data": {"serial": "0000000D30000299"},
        }
    )
    infrastructure.process_message(
        {
            "module": "netboot",
            "action": "revoke",
            "kind": "request",
            "data": {"serial": "0000000D300002AF"},
        }
    )

    def set_cmd(module, action, data):
        command = {"module": module, "action": action}
        if data:
            command["data"] = data
        res = infrastructure.process_message(
            {
                "module": "netboot",
                "kind": "request",
                "action": "command_set",
                "data": {"controller_id": "0000000D30000299", "command": command},
            }
        )
        assert res["data"]["result"] is True

    set_cmd("unset", "unset1", None)
    set_cmd("unset", "unset2", {})

    def unset_check(controller_id, module, action, result):
        notifications = infrastructure.get_notifications(filters=filters)

        res = infrastructure.process_message(
            {
                "module": "netboot",
                "kind": "request",
                "action": "command_unset",
                "data": {"controller_id": controller_id, "module": module, "action": action},
            }
        )

        assert res["data"]["result"] == result
        if result:
            # check notifications
            notifications = infrastructure.get_notifications(notifications, filters=filters)
            assert notifications[-1]["data"] == {
                "controller_id": controller_id,
                "module": module,
                "action": action,
            }

            # check not in whether list
            res = infrastructure.process_message(
                {"module": "netboot", "kind": "request", "action": "commands_list"}
            )
            controllers = [
                e for e in res["data"]["controllers"] if e["controller_id"] == controller_id
            ]
            if len(controllers) < 1:
                return

            assert len(controllers) == 1
            commands = [
                e
                for e in controllers[0]["commands"]
                if e["module"] == module and e["action"] == action
            ]
            assert len(commands) == 0

    # controller not in netboot list
    unset_check("0000000D30000312", "unset", "unset1", False)

    # controller in incoming
    unset_check("0000000D300002AF", "unset", "unset1", False)

    # controller in transfering
    unset_check("0000000D3000028E", "unset", "unset1", False)

    # success
    unset_check("0000000D30000299", "unset", "unset1", True)

    # command not found
    unset_check("0000000D30000299", "unset", "unset1", False)


def test_command_log(infrastructure, start_buses, init_netboot_devices):
    filters = [("netboot", "command_log")]

    infrastructure.process_message(
        {
            "module": "netboot",
            "action": "accept",
            "kind": "request",
            "data": {"serial": "0000000D30000299"},
        }
    )
    infrastructure.process_message(
        {
            "module": "netboot",
            "action": "revoke",
            "kind": "request",
            "data": {"serial": "0000000D300002AF"},
        }
    )

    def set_cmd(module, action, data):
        command = {"module": module, "action": action}
        if data:
            command["data"] = data
        res = infrastructure.process_message(
            {
                "module": "netboot",
                "kind": "request",
                "action": "command_set",
                "data": {"controller_id": "0000000D30000299", "command": command},
            }
        )
        assert res["data"]["result"] is True

    set_cmd("logged", "logged1", None)
    set_cmd("logged", "logged2", {})

    def log_check(controller_id, batch_id, module, action, result_to_store, expected_result):
        notifications = infrastructure.get_notifications(filters=filters)

        res = infrastructure.process_message(
            {
                "module": "netboot",
                "kind": "request",
                "action": "command_log",
                "data": {
                    "controller_id": controller_id,
                    "batch_id": batch_id,
                    "record": {"module": module, "action": action, "result": result_to_store},
                },
            }
        )

        assert res["data"]["result"] == expected_result

        if expected_result:
            # check notifications
            notifications = infrastructure.get_notifications(notifications, filters=filters)
            assert notifications[-1]["data"]["controller_id"] == controller_id
            assert notifications[-1]["data"]["batch_id"] == batch_id
            assert notifications[-1]["data"]["record"]["module"] == module
            assert notifications[-1]["data"]["record"]["action"] == action
            assert "when_stored" in notifications[-1]["data"]["record"]
            when_stored = notifications[-1]["data"]["record"]["when_stored"]
            assert notifications[-1]["data"]["record"]["result"] == result_to_store

            # check whether list
            res = infrastructure.process_message(
                {"module": "netboot", "kind": "request", "action": "commands_list"}
            )
            controllers = [
                e for e in res["data"]["controllers"] if e["controller_id"] == controller_id
            ]
            assert len(controllers) == 1
            batches = [e for e in controllers[0]["logs"] if e["batch_id"] == batch_id]
            assert len(batches) == 1
            records = [
                e for e in batches[0]["records"] if e["module"] == module and e["action"] == action
            ]
            assert len(records) > 0
            assert records[-1]["when_stored"] == when_stored
            assert records[-1]["result"] == result_to_store

    # controller not in netboot list
    log_check("0000000D30000312", "batch01", "logged", "logged1", True, False)

    # controller in incoming
    log_check("0000000D300002AF", "batch01", "logged", "logged1", True, False)

    # controller in transfering
    log_check("0000000D3000028E", "batch01", "logged", "logged1", True, False)

    # command not found
    log_check("0000000D30000299", "batch01", "notlogged", "logged1", True, False)
    log_check("0000000D30000299", "batch01", "logged", "logged3", True, False)

    # success
    log_check("0000000D30000299", "batch01", "logged", "logged1", True, True)
    log_check("0000000D30000299", "batch01", "logged", "logged1", True, True)

    # success with different batch
    log_check("0000000D30000299", "batch02", "logged", "logged2", False, True)
    log_check("0000000D30000299", "batch02", "logged", "logged2", True, True)
