

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
import shutil
import paramiko

# My program
from utils.utils import *
from utils.params import common_paths

#------------------------------------------------
# Functions
#------------------------------------------------

def prepare_honeypot(local_path):

	repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
	core_dir = os.path.join(repo_root, "core")

	if not os.path.exists(local_path):
		os.makedirs(local_path, exist_ok=True)

	# Copy the core honeypot runtime files
	for filename in [
		"honeypot.py",
		"rl_agent.py",
		"detection.py",
		"logger.py",
		"metrics.py",
		"session_manager.py",
	]:
		src = os.path.join(core_dir, filename)
		dst = os.path.join(local_path, filename)
		shutil.copy(src, dst)

	# Copy the response.db
	honeypot_dir = os.path.join(repo_root, "honeypot")
	response_src = os.path.join(honeypot_dir, "response.db")
	if os.path.exists(response_src):
		shutil.copy(response_src, local_path)
	else:
		print("[!] response.db not found in honeypot/. Creating honeypot instance without it.")

	# Copy the checkpoints of model
	checkpoint_dir = os.path.join(honeypot_dir, "checkpoints")
	os.makedirs(os.path.join(local_path, "checkpoints"), exist_ok=True)
	checkpoint_file = os.path.join(checkpoint_dir, "checkpoint")
	if os.path.exists(checkpoint_file):
		with open(checkpoint_file, "r") as f:
			lines = f.readlines()
		ckpt = lines[-1].split(" ")[-1].strip()
		shutil.copy(checkpoint_file, os.path.join(local_path, "checkpoints", "checkpoint"))
		for fname in os.listdir(checkpoint_dir):
			if ckpt in fname:
				shutil.copy(os.path.join(checkpoint_dir, fname), os.path.join(local_path, "checkpoints", fname))
	else:
		print("[!] No trained checkpoints found. Creating honeypot instance without model checkpoints.")

	# Copy the word2vec.bin
	word2vec_path = os.path.join(honeypot_dir, "word2vec.bin")
	if os.path.exists(word2vec_path):
		shutil.copy(word2vec_path, local_path)
	else:
		print("[!] No word2vec model found. The generated honeypot will run without Magnitude mode.")

	utils_local = os.path.join(local_path, "utils")
	os.makedirs(utils_local, exist_ok=True)
	for filename in ["oov.py", "model.py", "params.py", "http_headers.py"]:
		shutil.copy(os.path.join(repo_root, "utils", filename), os.path.join(utils_local, filename))

	# Copy the honeypot_setup.sh if it exists
	honeypot_setup_src = os.path.join(repo_root, "honeypot_setup.sh")
	if os.path.exists(honeypot_setup_src):
		shutil.copy(honeypot_setup_src, local_path)
	else:
		print("[!] honeypot_setup.sh not found in repo root; skipping setup script copy.")

def put_files(sftp, localdir, remotedir):

	for name in os.listdir(localdir):
		localpath = os.path.join(localdir, name)
		remotepath = os.path.join(remotedir, name) 
		
		if os.path.isdir(localpath):
			if not name in sftp.listdir(remotedir):
				sftp.mkdir(remotepath)
			put_files(sftp, localpath, remotepath)
		else:
			print(os.path.join(remotedir, name))
			sftp.put(localpath, remotepath)
		

def put_honeypot(ssh, localdir, remotedir):

	sftp = ssh.open_sftp()

	if not os.path.basename(os.path.dirname(localdir)) in sftp.listdir(remotedir):
		sftp.mkdir(localdir)

	remotedir = os.path.join(remotedir, localdir)

	put_files(sftp, localdir, remotedir)

	sftp.close()

def run_honeypot(ssh, localdir, remotedir, password):

	remotedir = os.path.join(remotedir, localdir)
	#stdin, stdout, stderr = ssh.exec_command("honeypot_setup.sh")
	#stdin, stdout, stderr = ssh.exec_command("cd " + remotedir + " && nohup sudo -S -p '' python3 honeypot.py &")
	stdin, stdout, stderr = ssh.exec_command("cd " + remotedir + " && echo " + password + " | nohup sudo -S python3 honeypot.py &")
	time.sleep(3)
	sys.exit(0)

def get_log(ssh, localdir, remotedir):

	sftp = ssh.open_sftp()

	remotedir = os.path.join(remotedir, localdir + common_paths["logs"])
	sftp.chdir(remotedir)

	sftp.get(remotedir + common_paths["access_log"], localdir + common_paths["access_log"])
	sftp.close()

	run_cmd('mv ' + localdir + common_paths["access_log"] + ' ./log.`date "+%Y%m%d-%H"`')

def stop_honeypot(ssh, localdir, remotedir, password):

	stdin, stdout, stderr = ssh.exec_command("echo " + password + " | sudo -S kill -KILL `ps aux | grep honeypot.py | awk '{print $2}'`")
	print("[*] stdout :", " ".join([out for out in stdout]))
	print("[*] stderr :", " ".join([out for out in stderr]))
	#run_cmd('rm -r ' + set_path + local_path)

def ssh_connect(remote_host, username, password):

	ssh = paramiko.SSHClient()
	ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
	ssh.connect(remote_host, username=username, password=password, timeout=10)
	
	return ssh 

#------------------------------------------------
# Main
#------------------------------------------------

def main():

	# [1] Prepare a directory for honeypot instance
	if args.create:
		prepare_honeypot(local_path)

	# SSH connection by paramiko
	if args.put or args.run or args.get or args.stop:
		ssh = ssh_connect(remote_host, username, password)

		# [2] push to instance
		if args.put:
			put_honeypot(ssh, local_path, set_path)

		# [3] start honeypot
		if args.run:
			run_honeypot(ssh, local_path, set_path, password)

		# [4] get log
		if args.get:
			get_log(ssh, local_path, set_path)

		# [5] stop honeypot
		if args.stop:
			stop_honeypot(ssh, local_path, set_path, password)

		# Close SSH connection
		ssh.close()

	print("[*] Finish!")


#------------------------------------------------
# if __name__ == '__main__'
#------------------------------------------------

if __name__ == '__main__':

	# Define Arguments
	parser = argparse.ArgumentParser(description='Create and manage the honeypot instance using SSH.')

	parser.add_argument('--create', action='store_true', help='<Flag> Create the honeypot instance.')
	parser.add_argument('--put', action='store_true', help='<Flag> Put the honeypot instance on the remote machine.')
	parser.add_argument('--run', action='store_true', help='<Flag> Run the honeypot on the remote machine.')
	parser.add_argument('--get', action='store_true', help='<Flag> Get the access log of the honeypot.')
	parser.add_argument('--stop', action='store_true', help='<Flag> Stop the honeypot on the remote machine.')

	parser.add_argument('-l', '--local', default=common_paths["instance"], help='Specify the path to the directory of the honeypot instance on the LOCAL machine(default: %s.' % common_paths["instance"])
	parser.add_argument('-r', '--remote', default="~", help='Specify the path to the directory of the honeypot instance will be put on the REMOTE machine. Check the directory permissions.')
	parser.add_argument('-i', '--ip', default="", help='Specify the IP address of the REMOTE machine.')
	parser.add_argument('-u', '--username', default="", help='Specify the username for ssh of the REMOTE machine.')
	parser.add_argument('-p', '--password', default="", help='Specify the password for ssh of the REMOTE machine.')
	parser.add_argument('-y', '--yes', action='store_true', help='Automatically answer yes to overwrite prompts.')

	args = parser.parse_args()

	# ----- Check Arguments -----

	# Flags
	if not (args.create or args.put or args.run or args.get or args.stop):
		print("[-] Select one or more flags.")
		sys.exit(1)

	# Instance Information
	remote_remote_host = args.ip
	username = args.username
	password = args.password
	if password == "":
		print("[!] No password entered. If you wish, you can hardcode the password.")

	remote_path = args.remote
	local_path = args.local
	if os.path.exists(local_path):
		if len(os.listdir(local_path)) != 0:
			print("[!] There are already files in %s" % local_path)
			print("[?] Do you want to allow overwriting?")
			if not (args.yes or yes_no_input()):
				print("[-] Finish")
				sys.exit(1)
	if not local_path.endswith("/"):
		local_path = local_path + "/"

	main()
