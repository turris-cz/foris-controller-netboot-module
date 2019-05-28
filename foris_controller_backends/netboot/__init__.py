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
import json
import typing
import pathlib

from datetime import datetime

from foris_controller.app import app_info
from foris_controller_backends.cmdline import BaseCmdLine, AsyncCommand
from foris_controller_backends.files import BaseFile, makedirs, path_exists
from foris_controller.utils import readlock, writelock, RWLock

logger = logging.getLogger(__name__)


class NetbootCmds(BaseCmdLine):
    def list(self) -> typing.List[dict]:
        retval, stdout, _ = self._run_command("/usr/bin/netboot-manager", "list-all", "-j")
        if retval != 0:
            return []
        try:
            parsed = json.loads(stdout)
            logger.debug("list obtained: %s", parsed)
            res = []
            for serial in parsed["accepted"]:
                res.append({"serial": serial, "state": "accepted"})
            for serial in parsed["incoming"]:
                res.append({"serial": serial, "state": "incoming"})
            for serial in parsed["transfering"]:
                res.append({"serial": serial, "state": "transfering"})
            return res

        except ValueError:
            logger.warn("failed to parse JSON")
        except KeyError:
            logger.warn("parsed JSON is not in correct format")

        return []

    def revoke(self, serial: str) -> bool:
        retval, stdout, _ = self._run_command("/usr/bin/netboot-manager", "revoke", serial)
        return retval == 0

    def accept(self, serial: str) -> bool:
        retval, stdout, _ = self._run_command("/usr/bin/netboot-manager", "accept", serial)
        return retval == 0


class NetbootFiles(BaseFile):
    command_lock = RWLock(app_info["lock_backend"])

    CMDS_FILE = "/etc/netboot/commands.json"
    LOGS_FILE = "/tmp/.netboot/cmd-logs.json"

    def _read(self, path: str, default=[]) -> dict:
        # create file if not present
        path_object = pathlib.Path(path)
        makedirs(str(path_object.parent))
        if not path_exists(path):
            self._store_to_file(path, json.dumps(default))

        return json.loads(self._file_content(path))

    def _write(self, path: str, content: dict) -> dict:
        self._store_to_file(path, json.dumps(content))

    def _command_exists(
        self, cmds_list: typing.List[dict], controller_id: str, module: str, action: str
    ) -> typing.Optional[typing.Tuple[int, dict]]:
        for cmd_record in cmds_list:
            if cmd_record["controller_id"] == controller_id:
                for (idx, record) in enumerate(cmd_record["commands"]):
                    if record["module"] == module and record["action"] == action:
                        return idx, cmd_record["commands"]
                break
        return None

    @readlock(command_lock, logger)
    def commands_list(self) -> typing.List[dict]:
        commands_list = self._read(NetbootFiles.CMDS_FILE)
        log_list = self._read(NetbootFiles.LOGS_FILE, {})

        for command in commands_list:
            controller_id = command["controller_id"]
            command["logs"] = log_list.get(controller_id, [])

        return commands_list

    @writelock(command_lock, logger)
    def command_set(
        self, controller_id: str, command: dict
    ) -> typing.Optional[typing.Tuple[str, str]]:
        commands_list = self._read(NetbootFiles.CMDS_FILE)

        # get controller record
        controller_record = None
        for cmd_record in commands_list:
            if cmd_record["controller_id"] == controller_id:
                controller_record = cmd_record
                break

        if not controller_record:
            controller_record = {"controller_id": controller_id, "commands": [], "logs": []}
            commands_list.append(controller_record)

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

        module = app_info["modules"].get(command_record["module"])
        if module:
            command_record["module_version"] = module.version
        else:
            command_record["module_version"] = "?"
        command_record["stored_time"] = datetime.utcnow().isoformat()

        # strore into disk
        self._write(NetbootFiles.CMDS_FILE, commands_list)

        return command_record["module_version"], command_record["stored_time"]

    @writelock(command_lock, logger)
    def command_unset(self, controller_id: str, module: str, action: str) -> bool:
        commands_list = self._read(NetbootFiles.CMDS_FILE)

        exists = self._command_exists(commands_list, controller_id, module, action)
        if not exists:
            return False

        idx, cmds = exists
        del cmds[idx]

        # strore into disk
        self._write(NetbootFiles.CMDS_FILE, commands_list)

        return True

    @writelock(command_lock, logger)
    def command_log(self, controller_id: str, batch_id: str, record: dict) -> bool:
        commands_list = self._read(NetbootFiles.CMDS_FILE)

        if not self._command_exists(
            commands_list, controller_id, record["module"], record["action"]
        ):
            return None

        # update log list
        log_dict = self._read(NetbootFiles.LOGS_FILE, {})
        logs = log_dict.get(controller_id, [])
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
        log_dict[controller_id] = logs

        # strore into disk
        self._write(NetbootFiles.LOGS_FILE, log_dict)

        return stored_time


class NetbootAsync(AsyncCommand):
    def accept(self, serial: str, notify: callable, reset_notifications: callable) -> str:
        def handler_exit(process_data):
            notify(
                {
                    "task_id": process_data.id,
                    "serial": serial,
                    "status": "succeeded" if process_data.get_retval() == 0 else "failed",
                }
            )

        def gen_handler(status):
            def handler(matched, process_data):
                notify({"task_id": process_data.id, "status": status, "serial": serial})

            return handler

        task_id = self.start_process(
            ["/usr/bin/netboot-manager", "accept", serial],
            [
                (r"^gen_ca: started.*$", gen_handler("started")),
                (r"^gen_ca: finished.*$", gen_handler("ca_ready")),
                (r"^gen_server: finished.*$", gen_handler("server_ready")),
                (r"^gen_client: finished.*$", gen_handler("client_ready")),
            ],
            handler_exit,
            reset_notifications,
        )

        return task_id
