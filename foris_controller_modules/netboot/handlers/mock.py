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
import copy

from foris_controller.handler_base import BaseMockHandler
from foris_controller.utils import logger_wrapper

from .. import Handler

logger = logging.getLogger(__name__)


class MockNetbootHandler(Handler, BaseMockHandler):
    devices = {
        "0000000D300002AF": "incoming",
        "0000000D30000299": "accepted",
        "0000000D3000028E": "transfering",
    }

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
    def accept(self, serial):
        if serial not in MockNetbootHandler.devices:
            return False
        if MockNetbootHandler.devices[serial] != "incoming":
            return False
        MockNetbootHandler.devices[serial] = "accepted"
        return True
