import importlib.util
import os
import sys
from pathlib import Path


APPLICATION_DIRECTORY = Path(__file__).resolve().parent / "employee_attendance_system"
application_directory = str(APPLICATION_DIRECTORY)
if application_directory not in sys.path:
    sys.path.insert(0, application_directory)

module_spec = importlib.util.spec_from_file_location(
    "_employee_attendance_system_app",
    APPLICATION_DIRECTORY / "app.py",
)
if module_spec is None or module_spec.loader is None:
    raise ImportError("Could not load the integrated attendance application.")
integrated_app = importlib.util.module_from_spec(module_spec)
sys.modules[module_spec.name] = integrated_app
module_spec.loader.exec_module(integrated_app)

create_app = integrated_app.create_app
app = integrated_app.app


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
        port=int(os.getenv("PORT", "5000")),
    )
