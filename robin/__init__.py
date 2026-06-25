"""
Emmy CLI - Unified command-line interface for Emmy.

Provides subcommands for:
- hermes chat          - Interactive chat (same as ./hermes)
- hermes gateway       - Run gateway in foreground
- hermes gateway start - Start gateway service
- hermes gateway stop  - Stop gateway service
- hermes setup         - Interactive setup wizard
- hermes status        - Show status of all components
- hermes cron          - Manage cron jobs
"""

import logging as _logging
import os
import sys

__version__ = "0.16.20"
__release_date__ = "2026.6.23"


def _install_emmy_log_branding() -> None:
    """Display log records under the ``emmy`` name, not the internal package name.

    The Python package is still called ``robin`` (a clean rename would touch 200+
    imports), so module loggers are named ``robin.*`` via ``getLogger(__name__)``.
    Rewriting the record's ``name`` at creation time relabels every log line (files,
    the desktop System-logs view, the gateway feed) to ``emmy.*`` without renaming the
    package. Level/config-by-logger-name still keys off the real logger, so this is
    display-only and functionally inert.
    """
    _prev = _logging.getLogRecordFactory()

    def _factory(*args, **kwargs):
        record = _prev(*args, **kwargs)
        name = record.name
        if name == "robin" or (isinstance(name, str) and name.startswith("robin.")):
            record.name = "emmy" + name[len("robin"):]
        return record

    _logging.setLogRecordFactory(_factory)


_install_emmy_log_branding()


def _ensure_utf8():
    """Force UTF-8 stdout/stderr on Windows to prevent UnicodeEncodeError.

    Windows services and terminals default to cp1252, which cannot encode
    box-drawing characters used in CLI output. This causes unhandled
    UnicodeEncodeError crashes on gateway startup.
    """
    if sys.platform != "win32":
        return
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            if getattr(stream, "encoding", "").lower().replace("-", "") != "utf8":
                new_stream = open(
                    stream.fileno(), "w", encoding="utf-8",
                    buffering=1, closefd=False,
                )
                setattr(sys, stream_name, new_stream)
        except (AttributeError, OSError):
            pass


_ensure_utf8()
