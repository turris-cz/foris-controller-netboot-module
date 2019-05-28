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

import logging
import random
import typing

from datetime import datetime

from foris_controller.handler_base import BaseMockHandler
from foris_controller.utils import logger_wrapper

from .. import Handler

logger = logging.getLogger(__name__)


class MockNetbootHandler(Handler, BaseMockHandler):
    devices: typing.Dict[str, str] = {
        "0000000D300002AF": "incoming",
        "0000000D30000299": "accepted",
        "0000000D3000028E": "transfering",
    }
    controllers: typing.List[dict] = []

    @logger_wrapper(logger)
    def list(self):
        return [{"serial": k, "state": v} for k, v in MockNetbootHandler.devices.items()]

    @logger_wrapper(logger)
    def revoke(self, serial):
        if serial not in MockNetbootHandler.devices:
            return False
        if MockNetbootHandler.devices[serial] != "accepted":
            return False
        MockNetbootHandler.devices[serial] = "incoming"
        return True

    @logger_wrapper(logger)
    def accept(self, serial: str, notify: callable, reset_notifications: callable):
        task_id = "%08X" % random.randrange(2 ** 32)
        notify({"task_id": task_id, "status": "started", "serial": serial})
        if (
            serial not in MockNetbootHandler.devices
            or MockNetbootHandler.devices[serial] != "incoming"
        ):
            notify({"task_id": task_id, "status": "failed", "serial": serial})
        else:
            MockNetbootHandler.devices[serial] = "accepted"
            notify({"task_id": task_id, "status": "succeeded", "serial": serial})
        return task_id

    @logger_wrapper(logger)
    def commands_list(self) -> typing.List[dict]:
        return MockNetbootHandler.controllers

    @logger_wrapper(logger)
    def command_set(
        self, controller_id: str, command: dict
    ) -> typing.Optional[typing.Tuple[str, str]]:
        if not MockNetbootHandler.devices.get(controller_id) == "accepted":
            return None

        # find controller
        controller_record = None
        for record in MockNetbootHandler.controllers:
            if record["controller_id"] == controller_id:
                controller_record = record
                break
        if not controller_record:
            # or insert new record
            controller_record = {"controller_id": controller_id, "commands": [], "logs": []}
            MockNetbootHandler.controllers.append(controller_record)

        # find command
        command_record = None
        for record in controller_record["commands"]:
            if record["module"] == command["module"] and record["action"] == command["action"]:
                command_record = record
        if not command_record:
            command_record = {"module": command["module"], "action": command["action"]}
            controller_record["commands"].append(command_record)

        # update command
        if "data" in command:
            command_record["data"] = command["data"]
        else:
            if "data" in command_record:
                del command_record["data"]

        from foris_controller.app import app_info

        module = app_info["modules"].get(command_record["module"])
        if module:
            command_record["module_version"] = module.version
        else:
            command_record["module_version"] = "?"
        command_record["stored_time"] = datetime.utcnow().isoformat()

        return command_record["module_version"], command_record["stored_time"]

    @logger_wrapper(logger)
    def command_unset(self, controller_id: str, module: str, action: str) -> bool:
        if not MockNetbootHandler.devices.get(controller_id) == "accepted":
            return False

        # find controller
        controllers = [
            e for e in MockNetbootHandler.controllers if e["controller_id"] == controller_id
        ]
        if len(controllers) != 1:
            return False

        # check whether the command is present
        if not [
            True
            for e in controllers[0]["commands"]
            if e["module"] == module and e["action"] == action
        ]:
            return False

        # remove record
        controllers[0]["commands"] = [
            e
            for e in controllers[0]["commands"]
            if not (e["module"] == module and e["action"] == action)
        ]

        return True

    @logger_wrapper(logger)
    def command_log(
        self, controller_id: str, batch_id: str, record: dict
    ) -> typing.Optional[typing.Tuple[str, str]]:
        if not MockNetbootHandler.devices.get(controller_id) == "accepted":
            return None

        controllers = [
            e for e in MockNetbootHandler.controllers if e["controller_id"] == controller_id
        ]
        if len(controllers) != 1:
            return None

        # check whether the command is present
        if not [
            True
            for e in controllers[0]["commands"]
            if e["module"] == record["module"] and e["action"] == record["action"]
        ]:
            return None

        logs = controllers[0]["logs"]
        batches = [e for e in logs if e["batch_id"] == batch_id]
        if batches:
            batch_records = batches[0]
        else:
            if len(logs) >= 10:
                logs.pop(0)
            # remove oldest batch if capacity was reached
            batch_records = {"batch_id": batch_id, "records": []}
            logs.append(batch_records)

        stored_time = datetime.utcnow().isoformat()
        batch_records["records"].append(
            {
                "module": record["module"],
                "action": record["action"],
                "result": record["result"],
                "when_stored": stored_time,
            }
        )
        return stored_time
