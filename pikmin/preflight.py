"""Import and parse the actual device commands without contacting an iPhone."""
import os
import subprocess
import sys

COMMANDS = (
    ('remote', 'tunneld'),
    ('developer', 'dvt', 'simulate-location', 'set'),
    ('developer', 'dvt', 'simulate-location', 'clear'),
    ('developer', 'dvt', 'screenshot'),
)


def check_command(command):
    environment = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'NO_COLOR': '1'}
    result = subprocess.run(
        [sys.executable, '-m', 'pymobiledevice3', *command, '--help'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        timeout=45, env=environment,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if result.returncode != 0 or 'Usage:' not in result.stdout:
        details = (result.stderr or result.stdout)[-2000:]
        raise RuntimeError(f"Device command failed to load: {' '.join(command)}\n{details}")


def main():
    for command in COMMANDS:
        check_command(command)
        print(f"OK: {' '.join(command)} (--help only)")


if __name__ == '__main__':
    main()
