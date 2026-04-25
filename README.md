# SmartPot / FirmPot

SmartPot is a Python-based workflow for turning OpenWrt firmware into an interactive honeypot. The repository includes:

- firmware boot and extraction helpers
- web UI scanning and request/response capture
- training for the response model
- honeypot instance generation
- a lightweight analytics dashboard
- end-to-end runner and verification scripts

The main entry points are:

- `scripts/verify_and_run.py`: full pipeline plus startup verification
- `scripts/run_all.py`: full pipeline runner without the extra verification summary
- `pipeline/scanner.py`: scanner/fuzzer stage
- `pipeline/learner.py`: model training stage
- `pipeline/manager.py --create`: assemble `honeypot_instance/`

## Supported Environment

Recommended host environment:

- Ubuntu 20.04 or similar Linux distribution
- Python `3.8.x`
- Docker available to the current user

This project currently targets Python 3.8 because the tested TensorFlow stack is pinned to `tensorflow==2.13.1`.

## System Dependencies

Install the required host packages before creating the virtual environment:

```bash
sudo apt update
sudo apt install -y \
  python3.8 python3.8-venv python3-dev build-essential \
  binwalk docker.io qemu-user-static file lsof iproute2 \
  firefox geckodriver
```

Notes:

- `binwalk` is required for firmware extraction. The original project documentation recommends `binwalk 2.2.x` for best compatibility.
- `docker` and `qemu-user-static` are required for emulating the extracted firmware.
- `firefox` and `geckodriver` are only required for Selenium-based crawling. If you use `pipeline/scanner.py --requests-only`, browser automation is skipped.
- The repository vendors a lightweight `simstring` compatibility package, so no separate `simstring` pip install is required.

Enable Docker after installation:

```bash
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Log out and back in after adding your user to the `docker` group.

## Python Setup

Create an isolated environment and install Python dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

## Repository Layout

Key directories:

- [`scripts/`](scripts): user-facing entry points
- [`pipeline/`](pipeline): firmware boot, scan, learn, and honeypot assembly steps
- [`core/`](core): honeypot runtime, dashboard, RL, and metrics logic
- [`utils/`](utils): shared utilities and data helpers
- [`simstring/`](simstring): vendored compatibility shim used by the OOV logic
- [`docs/`](docs): implementation notes

Generated runtime artifacts such as databases, checkpoints, extracted filesystems, and `honeypot_instance/` are intentionally ignored by Git.

## Running the Full Pipeline

From the repository root:

```bash
source venv/bin/activate
python3 scripts/verify_and_run.py /absolute/path/to/firmware.bin
```

Example:

```bash
python3 scripts/verify_and_run.py ./firmware/openwrt-firmware.bin
```

What this does:

1. validates the firmware path
2. checks host dependencies
3. runs the firmware-to-honeypot pipeline
4. verifies generated outputs
5. starts the honeypot and dashboard

## Running the Pipeline Step by Step

If you want to resume or debug the workflow manually:

```bash
source venv/bin/activate
python3 pipeline/booter.py /absolute/path/to/firmware.bin
python3 pipeline/scanner.py -i http://<container-ip>
python3 pipeline/learner.py -d ./core/
python3 pipeline/manager.py --create
```

Then start the generated honeypot from inside the runtime directory:

```bash
cd honeypot_instance
python3 honeypot.py -m
```

The `-m` flag enables the Magnitude/OOV path when `word2vec.bin` is present.

## Faster Iteration After Scanning

Scanning and fuzzing are often the slowest stage. If `core/learning.db`, `core/response.db`, `core/word2vec.bin`, and `core/checkpoints/` already exist, you can resume from the post-scan stages:

```bash
source venv/bin/activate
python3 pipeline/learner.py -d ./core/
python3 pipeline/manager.py --create
cd honeypot_instance
python3 honeypot.py -m
```

## Dashboard

Run the analytics dashboard in another terminal:

```bash
source venv/bin/activate
python3 core/analyzer.py --log-dir honeypot_instance/logs --honeypot-dir honeypot_instance --port 5000
```

Useful URLs:

- honeypot health: `http://127.0.0.1:8080/health`
- dashboard: `http://127.0.0.1:5000/dashboard`
- dashboard API: `http://127.0.0.1:5000/api/stats`

## Browser Scanner Notes

`pipeline/scanner.py` supports two modes:

- Selenium-based crawling with Firefox
- `--requests-only` mode for faster HTTP-only scanning

Examples:

```bash
python3 pipeline/scanner.py -i http://172.20.0.2
python3 pipeline/scanner.py --requests-only -i http://172.20.0.2
```

If the target login flow is unusual, check `utils/login.py` and the scanning parameters in [`utils/params.py`](utils/params.py).

## Common Operational Notes

- Run `honeypot.py` from inside `honeypot_instance/`, not from the repository root. The runtime uses relative paths for `response.db`, `word2vec.bin`, and `checkpoints/`.
- If port `8080` is already in use, stop the previous honeypot process or start on another port with `python3 honeypot.py -m -p 8081`.
- The project is Linux-first. Docker, QEMU user emulation, and firmware extraction are not expected to work on Windows without significant adaptation.

## GitHub Readiness Notes

This repository is configured to avoid committing:

- virtual environments
- extracted firmware trees
- generated databases
- trained checkpoints
- logs and runtime files
- large firmware images and binaries

Before pushing, verify the working tree is clean:

```bash
git status
```

If you have old generated artifacts already tracked in your local branch, remove them from the index before your first push:

```bash
git rm --cached -r honeypot_instance extracted_fs _*.extracted core/checkpoints core/*.db core/word2vec.bin logs scripts/logs core/logs
```

## Troubleshooting

### `binwalk: not found`

Install the system package and verify it is on `PATH`:

```bash
sudo apt install -y binwalk
binwalk --version
```

### `docker not found` or Docker permission errors

Install Docker, start the service, and make sure your user is in the `docker` group.

### `No such file or directory: response.db`

Start the honeypot from `honeypot_instance/`, or rerun:

```bash
python3 pipeline/manager.py --create
```

### Scanner takes too long

Use `--requests-only` or resume from the post-scan stages described above.

## Suggested Next Cleanup

The repository is now safe to publish, but these follow-up changes would make it even cleaner:

- move historical material under `archive/` behind a clearer `legacy/` boundary
- consolidate duplicated quickstart content from `QUICKSTART.md` into this README
- move vendored `simstring/` sources into a dedicated `third_party/` directory
- add a small `scripts/resume_after_scan.sh` helper for the post-scan workflow
