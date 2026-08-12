#!/usr/bin/env python3
"""Regenerate the current independent manuscript panels from canonical data.

This public entrypoint delegates to the presentation-only renderer.  It reads
only compact canonical CSV/JSON artifacts, verifies every input SHA-256 before
and after rendering, and writes PDF/EPS/PNG outputs below
``build/figure_reproduction``.  It does not run a scientific experiment.
"""

from manuscript_panel_renderer import main


if __name__ == "__main__":
    raise SystemExit(main())
