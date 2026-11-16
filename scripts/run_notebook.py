"""Execute a Jupyter notebook end to end, failing on any cell error.

Usage: ``python scripts/run_notebook.py NOTEBOOK [--output PATH]``.
With ``--output`` the executed notebook, outputs included, is saved.
"""

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import nbformat
from nbclient import NotebookClient

# Seconds one cell may run before the execution is aborted.
CELL_TIMEOUT_SECONDS: Final = 120
KERNEL_NAME: Final = "python3"


def execute_notebook(
    notebook_path: Path,
    timeout_seconds: int = CELL_TIMEOUT_SECONDS,
    kernel_name: str = KERNEL_NAME,
) -> nbformat.NotebookNode:
    """Run every cell of a notebook in its own directory.

    Args:
        notebook_path: Notebook to execute.
        timeout_seconds: Limit for a single cell.
        kernel_name: Jupyter kernel to run the cells with.

    Returns:
        The notebook with fresh outputs.

    Raises:
        nbclient.exceptions.CellExecutionError: If a cell fails.
    """
    notebook = nbformat.read(notebook_path, as_version=nbformat.NO_CONVERT)
    client = NotebookClient(
        notebook,
        timeout=timeout_seconds,
        kernel_name=kernel_name,
        resources={"metadata": {"path": str(notebook_path.parent)}},
    )
    return client.execute()


def main(argv: Sequence[str] | None = None) -> None:
    """Execute the notebook named on the command line.

    Args:
        argv: Arguments without the program name; None reads
            ``sys.argv``.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("notebook", type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    executed = execute_notebook(arguments.notebook)
    if arguments.output is not None:
        nbformat.write(executed, arguments.output)


if __name__ == "__main__":
    main()
