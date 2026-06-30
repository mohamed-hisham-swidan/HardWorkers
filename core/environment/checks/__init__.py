"""Registry of all environment checks."""

from core.environment.checks.ai_provider_check import AIProviderCheck
from core.environment.checks.config_check import ConfigCheck
from core.environment.checks.database_check import DatabaseCheck
from core.environment.checks.filesystem_check import FilesystemCheck
from core.environment.checks.hardware_check import HardwareCheck
from core.environment.checks.os_check import OSCheck
from core.environment.checks.package_check import PackageCheck
from core.environment.checks.python_check import PythonCheck

__all__ = [
    "PythonCheck",
    "PackageCheck",
    "FilesystemCheck",
    "ConfigCheck",
    "DatabaseCheck",
    "AIProviderCheck",
    "OSCheck",
    "HardwareCheck",
]

ALL_CHECKS = [
    PythonCheck,
    PackageCheck,
    FilesystemCheck,
    ConfigCheck,
    DatabaseCheck,
    AIProviderCheck,
    OSCheck,
    HardwareCheck,
]
