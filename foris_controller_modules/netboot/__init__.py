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

from foris_controller.module_base import BaseModule
from foris_controller.handler_base import wrap_required_functions


class NetbootModule(BaseModule):
    logger = logging.getLogger(__name__)

    def action_accept(self, data):
        def notify(msg: dict):
            self.notify("accept", msg)

        async_id = self.handler.accept(data["serial"], notify, self.reset_notify)

        return {"task_id": async_id}

    def action_revoke(self, data):
        res = {}
        res = self.handler.revoke(data["serial"])
        if res:
            self.notify("revoke", data)
        return {"result": res}

    def action_list(self, data):
        return {"devices": self.handler.list()}

    def action_commands_list(self, data: dict) -> dict:
        return {"controllers": self.handler.commands_list()}

    def action_command_set(self, data: dict) -> dict:
        res = self.handler.command_set(**data)
        if res is not None:
            data["command"]["module_version"], data["command"]["stored_time"] = res
            self.notify("command_set", data)
        return {"result": True if res else False}

    def action_command_unset(self, data: dict) -> dict:
        res = self.handler.command_unset(**data)
        if res:
            self.notify("command_unset", data)
        return {"result": res}

    def action_command_log(self, data: dict) -> dict:
        res = self.handler.command_log(**data)
        if res is not None:
            data["record"]["when_stored"] = res
            self.notify("command_log", data)
        return {"result": True if res else False}


@wrap_required_functions(
    ["revoke", "accept", "list", "commands_list", "command_set", "command_unset", "command_log"]
)
class Handler(object):
    pass
