import pathlib

"""
The root folder has a file called settings.py
recurses until settings.py is found to find the absolute path of the root project folder
"""
def get_project_root(file_path):
    """Finds the project root directory from any file within the project."""
    path = pathlib.Path(file_path).resolve()

    while True:
        if (path / "settings.py").exists():
            return path
        if path == path.parent:
            raise FileNotFoundError("Could not find project root directory.")
        path = path.parent


PROJECT_ROOT_DIR = get_project_root(__file__)