"""Hardware resource validation (RAM, disk, CPU)."""

from __future__ import annotations

import os
from typing import Any

from core.environment.models import Severity, ValidationResult

MINIMUM_RAM_MB = 2048
RECOMMENDED_RAM_MB = 4096

MINIMUM_DISK_GB = 1
RECOMMENDED_DISK_GB = 5

MINIMUM_CPU_COUNT = 2
RECOMMENDED_CPU_COUNT = 4


class HardwareCheck:
    def __init__(self, config: Any = None) -> None:
        self._config = config
        self._psutil_available = self._check_psutil()

    def run(self) -> ValidationResult:
        failures: list[str] = []
        warnings: list[str] = []

        ram_info = self._get_ram_info()
        disk_info = self._get_disk_info()
        cpu_info = self._get_cpu_info()

        if ram_info["total_mb"] is not None and ram_info["total_mb"] < MINIMUM_RAM_MB:
            failures.append(f"RAM ({ram_info['total_mb']:.0f} MB) below minimum {MINIMUM_RAM_MB} MB")
        elif ram_info["total_mb"] is not None and ram_info["total_mb"] < RECOMMENDED_RAM_MB:
            warnings.append(f"RAM ({ram_info['total_mb']:.0f} MB) below recommended {RECOMMENDED_RAM_MB} MB")

        if disk_info["free_gb"] is not None and disk_info["free_gb"] < MINIMUM_DISK_GB:
            failures.append(f"Free disk ({disk_info['free_gb']:.1f} GB) below minimum {MINIMUM_DISK_GB} GB")
        elif disk_info["free_gb"] is not None and disk_info["free_gb"] < RECOMMENDED_DISK_GB:
            warnings.append(f"Free disk ({disk_info['free_gb']:.1f} GB) below recommended {RECOMMENDED_DISK_GB} GB")

        if cpu_info["count"] is not None and cpu_info["count"] < MINIMUM_CPU_COUNT:
            failures.append(f"CPU cores ({cpu_info['count']}) below minimum {MINIMUM_CPU_COUNT}")
        elif cpu_info["count"] is not None and cpu_info["count"] < RECOMMENDED_CPU_COUNT:
            warnings.append(f"CPU cores ({cpu_info['count']}) below recommended {RECOMMENDED_CPU_COUNT}")

        overall = len(failures) == 0
        severity = Severity.CRITICAL if failures else Severity.WARNING if warnings else Severity.INFO

        return ValidationResult(
            name="Hardware",
            success=overall,
            severity=severity,
            message="Hardware check complete — resources are adequate."
            if overall and not warnings
            else f"Hardware issues: {len(failures)} failures, {len(warnings)} warnings.",
            details={
                "ram": ram_info,
                "disk": disk_info,
                "cpu": cpu_info,
                "psutil_available": self._psutil_available,
                "failures": failures,
                "warnings": warnings,
                "minimums": {
                    "ram_mb": MINIMUM_RAM_MB,
                    "disk_gb": MINIMUM_DISK_GB,
                    "cpu_count": MINIMUM_CPU_COUNT,
                },
                "recommended": {
                    "ram_mb": RECOMMENDED_RAM_MB,
                    "disk_gb": RECOMMENDED_DISK_GB,
                    "cpu_count": RECOMMENDED_CPU_COUNT,
                },
            },
            recommendation="Free up system resources or upgrade hardware." if failures else "",
        )

    @staticmethod
    def _check_psutil() -> bool:
        try:
            import psutil  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_ram_info(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "total_mb": None,
            "available_mb": None,
            "percent_used": None,
            "source": "os",
        }
        if self._psutil_available:
            try:
                import psutil

                mem = psutil.virtual_memory()
                result["total_mb"] = mem.total / (1024 * 1024)
                result["available_mb"] = mem.available / (1024 * 1024)
                result["percent_used"] = mem.percent
                result["source"] = "psutil"
                return result
            except Exception:
                pass

        if hasattr(os, "sysconf"):
            try:
                pages = os.sysconf("SC_PHYS_PAGES")
                page_size = os.sysconf("SC_PAGE_SIZE")
                result["total_mb"] = (pages * page_size) / (1024 * 1024)
                result["source"] = "os.sysconf"
            except (ValueError, KeyError, AttributeError):
                pass

        return result

    def _get_disk_info(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "total_gb": None,
            "free_gb": None,
            "percent_used": None,
            "source": "os",
        }
        if self._psutil_available:
            try:
                import psutil

                disk = psutil.disk_usage(".")
                result["total_gb"] = disk.total / (1024**3)
                result["free_gb"] = disk.free / (1024**3)
                result["percent_used"] = disk.percent
                result["source"] = "psutil"
                return result
            except Exception:
                pass

        try:
            st = os.statvfs(".")
            free = st.f_bavail * st.f_frsize
            total = st.f_blocks * st.f_frsize
            result["total_gb"] = total / (1024**3)
            result["free_gb"] = free / (1024**3)
            result["percent_used"] = ((total - free) / total) * 100
            result["source"] = "os.statvfs"
        except (AttributeError, OSError):
            pass

        return result

    @staticmethod
    def _get_cpu_info() -> dict[str, Any]:
        result: dict[str, Any] = {
            "count": None,
            "physical_count": None,
            "source": "os",
        }
        try:
            import psutil

            result["count"] = psutil.cpu_count(logical=True)
            result["physical_count"] = psutil.cpu_count(logical=False)
            result["source"] = "psutil"
            return result
        except ImportError:
            pass

        try:
            result["count"] = os.cpu_count()
            result["source"] = "os.cpu_count"
        except AttributeError:
            pass

        return result
