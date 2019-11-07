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

import argparse
import logging
import re
import sys
import uuid
import time
import typing

from foris_controller_netboot_module import __version__
from foris_controller.utils import read_passwd_file

logger = logging.getLogger(__file__)

TIMEOUT: int = 5000  # in ms
LOGGER_MAX_LEN = 10000
MIN_SETUP_RETRY = 30.0  # in secods


CHECK_RESULTS: typing.Dict[str, typing.Callable[[dict], bool]] = {
    "default": lambda data: True if data == {"result": True} else False
}


def main():
    # Parse the command line options
    parser = argparse.ArgumentParser(prog="foris-netboot-observer")
    parser.add_argument("-d", "--debug", dest="debug", action="store_true", default=False)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--controller-id",
        type=lambda x: re.match(r"[0-9a-zA-Z]{16}", x).group().upper(),
        help="host controller id (the one which manages netbooted devices)",
    )
    parser.add_argument("--host", dest="host", default="localhost")
    parser.add_argument("--port", dest="port", type=int, default=1883)
    parser.add_argument(
        "--passwd-file",
        type=lambda x: read_passwd_file(x),
        help="path to passwd file (first record will be used to authenticate)",
        default=None,
    )

    options = parser.parse_args()

    logging_format = "%(levelname)s:%(name)s:%(message)." + str(LOGGER_MAX_LEN) + "s"
    if options.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(threadName)s: " + logging.BASIC_FORMAT)
    else:
        logging.basicConfig(format=logging_format)

    logger.debug("Version %s" % __version__)

    try:
        from foris_client.buses import mqtt
        from foris_client.buses.base import prepare_controller_id, ControllerError
    except ImportError:
        logger.error("Failed to import foris_client.")
        sys.exit(0)

    host_controller_id = prepare_controller_id(options.controller_id)

    # instanticate sender
    sender = mqtt.MqttSender(
        options.host, options.port, TIMEOUT, credentials=options.passwd_file  # fixed timeout in ms
    )

    last_used: typing.Dict[str, float] = {}

    def listen_handler(data, controller_id):
        try:
            logger.debug(f"Notification from {controller_id} {data['module']}.{data['action']}")
            if controller_id == host_controller_id:
                logger.debug("Skip host notifications (%s)", controller_id)
                return

            if data["module"] != "remove" and data["action"] != "advertize":
                logger.debug("Other notification.")
                return

            if data["data"]["netboot"] != "booted":
                logger.debug("Not under netboot or already configured (%s)", controller_id)
                return

            # don't try to setup up to the same controller to recently
            # wait at least MIN_SETUP_RETRY before retry
            last_used_time: float = last_used.get(controller_id, 0.0)
            if time.time() - last_used_time < MIN_SETUP_RETRY:
                logger.debug("Was configured to recently (%s)", controller_id)
                return
            last_used[controller_id] = time.time()

            # Get commands for particular controller id
            resp = sender.send("netboot", "commands_list", None, controller_id=host_controller_id)
            if "error" in resp:
                logger.warning("Error occured.")
                return

            # find controller_id
            controllers = [e for e in resp["controllers"] if e["controller_id"] == controller_id]
            if len(controllers) == 0 or len(controllers[0]["commands"]) == 0:
                logger.debug("No commands ('%s')", controller_id)
                # nothing to configure, mark as configured and exit
                sender.send("remote", "set_netboot_configured", None, controller_id=controller_id)
                return

            commands = controllers[0]["commands"]
            batch_id = str(uuid.uuid4())

            def log_command(command: dict, result: bool):
                logger.debug("Logging '%s.%s'", command["module"], command["action"])
                sender.send(
                    "netboot",
                    "command_log",
                    {
                        "controller_id": controller_id,
                        "batch_id": batch_id,
                        "record": {
                            "module": command["module"],
                            "action": command["action"],
                            "result": result,
                        },
                    },
                    controller_id=host_controller_id,
                )
                logger.debug("Logged '%s.%s'", command["module"], command["action"])

            for command in commands:
                try:
                    command_resp = sender.send(
                        command["module"],
                        command["action"],
                        command.get("data"),
                        controller_id=controller_id,
                    )
                    checker = CHECK_RESULTS.get(
                        f"{command['module']}.{command['action']}", CHECK_RESULTS["default"]
                    )
                    result = checker(command_resp)
                    log_command(command, result)
                except ControllerError:
                    log_command(command, False)

            # set configured
            sender.send("remote", "set_netboot_configured", None, controller_id=controller_id)
        except ControllerError as e:
            logger.error("Netbooted device configuration failed at some point.")
            logger.error(str(e))
            logger.debug("%s", e.errors[0]["description"])
            logger.debug("%s", e.errors[0]["stacktrace"])

    listener = mqtt.MqttListener(
        options.host,
        options.port,
        listen_handler,
        "remote",
        None,
        tls_files=None,
        controller_id="+",  # listen to all controllers
        credentials=options.passwd_file,
    )

    listener.listen()


if __name__ == "__main__":
    main()
