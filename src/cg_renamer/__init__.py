"""CG Asset Renamer - a configurable renaming & naming-check tool for Maya 2025.3."""

from .naming_convention import NamingConvention, ValidationResult
from .renamer import Renamer

__version__ = "1.0.0"

__all__ = ["NamingConvention", "ValidationResult", "Renamer", "__version__"]
