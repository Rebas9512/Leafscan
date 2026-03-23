"""
leafhub_dist — LeafHub integration module (distributed copy).

Written by ``leafhub register`` / ``leafhub project link`` on first
registration.  Provides offline-capable shell integration (register.sh)
and stdlib-only detection (probe.py) for the project's venv.

Contents
--------
register.sh       Shell function for setup scripts (leafhub_setup_project).
probe.py          Stdlib-only runtime detection (detect → open_sdk → get_key).
setup_template.sh Ready-to-use setup.sh starting point for new projects.
LEAFHUB.md        Full integration protocol and code templates.

Two-tier dependency model
--------------------------
probe.detect()   — stdlib only; works without the leafhub pip package.
found.open_sdk() — requires the ``leafhub`` pip package (imports leafhub.sdk).

See LEAFHUB.md for the complete integration guide.
Do not edit these files manually — refreshed by: leafhub register <project>
"""
from .probe import detect, register, ProbeResult

__leafhub_dist_version__ = 2

__all__ = ["detect", "register", "ProbeResult", "__leafhub_dist_version__"]
