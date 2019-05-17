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
import re
import typing

from foris_controller_backends.cmdline import BaseCmdLine, AsyncCommand
from foris_controller_backends.uci import UciBackend, get_option_named

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
