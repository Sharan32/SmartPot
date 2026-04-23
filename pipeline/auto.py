
#------------------------------------------------
# Import
#------------------------------------------------

import os
import sys
sys.dont_write_bytecode = True

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import time
import argparse
import subprocess

# My program
from utils.utils import run_cmd, docker_cmd
from utils.params import common_paths, docker_config

#------------------------------------------------
# Main
#------------------------------------------------

def main():

    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

    # [1] Booter
    print("[*] Run booter.py")
    booter_result = subprocess.run(
        ["python3", "pipeline/booter.py", firmware_path, "-c", str(container_num), "--yes"],
        env=env
    )
    if booter_result.returncode != 0:
        print(f"[-] booter.py failed with exit code {booter_result.returncode}.")
        sys.exit(1)

    # [2] Scanner
    ip_list = []
    for i in range(container_num):
        container_name =  docker_config["container_name"] + str(i)
        cmd = docker_cmd("inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' " + container_name)
        result = run_cmd(cmd)

        if len(result) > 0 and result[0]:
            ip_list.append(result[0])
    print("[*] Number of containers successfully launched :", len(ip_list))


    if len(ip_list) > 0:
        print("[*] Run scanner.py")
        scanner_result = subprocess.run(
            ["python3", "pipeline/scanner.py", "--requests-only", "-i"] + ["http://" + ip for ip in ip_list],
            env=env
        )
        if scanner_result.returncode != 0:
            print(f"[-] scanner.py failed with exit code {scanner_result.returncode}.")
            sys.exit(1)
        #subprocess.run(["python3", "scanner.py", "-i"] + ["https://" + ip for ip in ip_list])
    else:
        print("[-] booter.py failed.")
        sys.exit(1)

    # [3] Learner
    print("[*] Run learner.py")
    learner_result = subprocess.run(["python3", "pipeline/learner.py"], env=env)
    if learner_result.returncode != 0:
        print(f"[-] learner.py failed with exit code {learner_result.returncode}.")
        sys.exit(1)
 
    # [4] Manager
    print("[*] Run manager.py")
    manager_result = subprocess.run(["python3", "pipeline/manager.py", "--create", "--yes"], env=env)
    if manager_result.returncode != 0:
        print(f"[-] manager.py failed with exit code {manager_result.returncode}.")
        sys.exit(1)

    print("[*] Finish!")


#------------------------------------------------
# if __name__ == '__main__'
#------------------------------------------------

if __name__ == '__main__':

    # Define Arguments
    parser = argparse.ArgumentParser(description='Automatically generate a honeypot.')
    parser.add_argument('firmware', help="Specify the path to the firmware image.")
    parser.add_argument('-c', '--containers', default=1, type=int, help="Specify the number of containers to be launched, or 0 if you don't want to launch any (default: 1).")
    args = parser.parse_args()

    # ----- Check Arguments -----

    # Path to firmware image
    firmware_path = args.firmware
    if not os.path.exists(firmware_path):
        print("[-] The path to the firmware image is incorrect.")
        sys.exit(1)

    # Number of containers to run
    container_num = args.containers

    main()
