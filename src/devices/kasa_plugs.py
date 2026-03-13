"""Kasa smart plug control helpers."""

import json
import subprocess
from datetime import datetime

from ..core.config import chiller_id, variac_id


class KasaPlugs:
    """Control Kasa smart plugs through kasa_smartPlug.py."""

    def chiller_state(self, cmd):
        """Use True for on, False for off."""
        self.run_script("cataverse_venv", "kasa_smartPlug.py", chiller_id, cmd)

    def variac_state(self, cmd):
        """Use True for on, False for off."""
        self.run_script("cataverse_venv", "kasa_smartPlug.py", variac_id, cmd)

    def kasaPlug_state(self, plug_id, cmd):
        """Use True for on, False for off."""
        self.run_script(".venv", "kasa_smartPlug.py", plug_id, cmd)

    def run_script(self, env, script, *args):
        def log(message):
            print("{}: {}".format(datetime.now(), message))

        if env == ".venv":
            python_path = "C:\\Users\\labuser\\CataVerse\\.venv\\Scripts\\python.exe"
        else:
            python_path = "C:\\Program Files\\Python312\\python.exe"  # this is not a path

        script_path = f"C:\\Users\\labuser\\CataVerse\\{script}"
        serialized_args = [
            json.dumps(arg) if isinstance(arg, list) else str(arg) for arg in args
        ]

        try:
            process = subprocess.Popen(
                [python_path, script_path] + serialized_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            try:
                output, error = process.communicate(timeout=30)
                print(output.decode())
            except subprocess.TimeoutExpired:
                process.kill()
                log("Process killed after timeout")
                output, error = process.communicate()
                log(f"Output:\n{output.decode()}")
                log(f"Error:\n{error.decode()}")
        except Exception as e:
            log(f"An error occurred: {e}")
        finally:
            if process.poll() is None:
                process.kill()
                log("Process forcefully killed")
