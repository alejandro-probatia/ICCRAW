"""NexoRAW public compatibility package.

The implementation still lives in :mod:`iccraw` so existing scripts and imports
continue to work during the project rename.
"""

from iccraw.version import __version__

__all__ = ["__version__"]
