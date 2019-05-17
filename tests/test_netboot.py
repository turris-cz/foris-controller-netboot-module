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
