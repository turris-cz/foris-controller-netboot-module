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
import typing

from foris_controller.handler_base import BaseOpenwrtHandler
from foris_controller.utils import logger_wrapper

from foris_controller_backends.netboot import NetbootCmds, NetbootAsync, NetbootFiles

from .. import Handler

logger = logging.getLogger(__name__)


class OpenwrtNetbootHandler(Handler, BaseOpenwrtHandler):

    cmds = NetbootCmds()
    async_cmds = NetbootAsync()
    files = NetbootFiles()

    def _netboot_serial_exists(self, serial):
        return serial in [
            e["serial"] for e in OpenwrtNetbootHandler.cmds.list() if e["state"] == "accepted"
        ]

    @logger_wrapper(logger)
    def list(self):
        return OpenwrtNetbootHandler.cmds.list()

    @logger_wrapper(logger)
    def revoke(self, serial: str):
        return OpenwrtNetbootHandler.cmds.revoke(serial)

    @logger_wrapper(logger)
    def accept(self, serial: str, notify: callable, reset_notifications: callable):
        return OpenwrtNetbootHandler.async_cmds.accept(serial, notify, reset_notifications)

    @logger_wrapper(logger)
    def commands_list(self) -> typing.List[dict]:
        return OpenwrtNetbootHandler.files.commands_list()

    @logger_wrapper(logger)
    def command_set(
        self, controller_id: str, command: dict
    ) -> typing.Optional[typing.Tuple[str, str]]:
        if not self._netboot_serial_exists(controller_id):
            return None
        return OpenwrtNetbootHandler.files.command_set(controller_id, command)

    @logger_wrapper(logger)
    def command_unset(self, controller_id: str, module: str, action: str) -> bool:
        if not self._netboot_serial_exists(controller_id):
            return False
        return OpenwrtNetbootHandler.files.command_unset(controller_id, module, action)

    @logger_wrapper(logger)
    def command_log(
        self, controller_id: str, batch_id, record: dict
    ) -> typing.Optional[typing.Tuple[str, str]]:
        if not self._netboot_serial_exists(controller_id):
            return None
        return OpenwrtNetbootHandler.files.command_log(controller_id, batch_id, record)
