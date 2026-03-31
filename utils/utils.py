
#------------------------------------------------
# Import
#------------------------------------------------

import os
import sys
import subprocess

#------------------------------------------------
# Functions
#------------------------------------------------

def run_cmd(cmd):
    """ Run the shell command specified in <cmd> """
    result = subprocess.Popen(cmd, stdout=subprocess.PIPE, shell=True).stdout.readlines()
    return [x.decode().rstrip("\n") for x in result]


def docker_prefix():
    """Return docker command prefix based on current privileges/environment."""
    mode = os.getenv("FIRMPOT_DOCKER_SUDO", "auto").strip().lower()

    if mode in ["1", "true", "yes", "on"]:
        return "sudo docker"
    if mode in ["0", "false", "no", "off"]:
        return "docker"

    rc = subprocess.call(
        "docker ps >/dev/null 2>&1",
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if rc == 0:
        return "docker"
    return "sudo docker"


def docker_cmd(args):
    return docker_prefix() + " " + args

def yes_no_input():
    if not sys.stdin.isatty():
        # Non-interactive execution defaults to yes unless overridden.
        assume_yes = os.getenv("FIRMPOT_ASSUME_YES", "1").strip().lower()
        return assume_yes not in ["0", "false", "no", "off"]

    while True:
        try:
            choice = input("Please respond with 'yes' or 'no' [Y/n]: ").lower()
        except EOFError:
            assume_yes = os.getenv("FIRMPOT_ASSUME_YES", "1").strip().lower()
            return assume_yes not in ["0", "false", "no", "off"]
        if choice in ['y', 'ye', 'yes', 'Y', 'YE', 'YES', '']:
            return True
        elif choice in ['n', 'no', 'N', 'NO']:
            return False
