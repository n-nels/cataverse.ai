## gui.py

from PyQt5 import QtWidgets, uic
from script_executor import ScriptExecutor

class GUI:
    """Class to manage the graphical user interface for device control."""

    def __init__(self):
        """Initializes the GUI with default settings."""
        self.app = QtWidgets.QApplication([])
        self.window = QtWidgets.QMainWindow()
        self.script_executor = ScriptExecutor()
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Sets up the user interface components."""
        # Load the UI from a .ui file or set up manually
        # For demonstration, we assume a simple setup
        self.window.setWindowTitle("Device Control Interface")
        self.window.setGeometry(100, 100, 800, 600)

        # Create buttons and connect them to methods
        self.load_script_button = QtWidgets.QPushButton("Load Script", self.window)
        self.load_script_button.setGeometry(50, 50, 200, 40)
        self.load_script_button.clicked.connect(self._load_script)

        self.manual_control_button = QtWidgets.QPushButton("Manual Control", self.window)
        self.manual_control_button.setGeometry(50, 100, 200, 40)
        self.manual_control_button.clicked.connect(self.manual_control)

    def start_interface(self) -> None:
        """Starts the graphical user interface."""
        self.window.show()
        self.app.exec_()

    def load_script(self, file_path: str) -> None:
        """Loads a script from the specified file path.

        Args:
            file_path: The path to the script file to load.
        """
        try:
            with open(file_path, 'r') as file:
                script = file.read()
                self.script_executor.execute_script(script)
                print(f"Script loaded and executed from {file_path}")
        except FileNotFoundError:
            print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Failed to load script from {file_path}: {e}")

    def manual_control(self) -> None:
        """Enables manual control of the devices."""
        # Placeholder for manual control logic
        # Example: Open a new window or dialog for manual control
        print("Manual control activated.")
        # Add specific manual control logic here

    def _load_script(self) -> None:
        """Opens a file dialog to select and load a script."""
        options = QtWidgets.QFileDialog.Options()
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self.window, "Open Script File", "", "All Files (*);;Python Files (*.py)", options=options)
        if file_path:
            self.load_script(file_path)
