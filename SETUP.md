# AstroPi v0.1 — read-only status page

This first build only inspects USB enumeration, the mounted acquisition-drive UUID and Pi health. It cannot expose, capture, move, Home, Park or track the telescope.

Run on the Raspberry Pi (already cloned as ~/astropi):

    sudo apt install -y python3-venv
    cd ~/astropi
    git pull --ff-only
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    python -m pytest -q
    python run.py --host 0.0.0.0 --port 8080

From another device on the trusted LAN open http://astropi.local:8080/ (or use the Pi's LAN IP if mDNS fails). Stop with Ctrl+C.

This runs Flask's development server, not a configured systemd service. It has no authentication; do not expose the port to the Internet. Port already in use? Choose --port 8081 and change the browser URL. To run again use: cd ~/astropi && source .venv/bin/activate && python run.py

The camera and mount labels indicate USB presence only, NOT an SDK/serial connection. Recording-drive ready requires the exact verified filesystem UUID on its expected mount. When the drive is missing, the status service never writes to the underlying microSD directory. Re-check the drive before every actual write in the future capture implementation. All browsers are viewers until operator-lease controls are implemented.
