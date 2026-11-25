"""Browser-accessible developer tools."""

from __future__ import annotations

from flask import Blueprint, render_template

web_bp = Blueprint("web", __name__)


@web_bp.get("/debug")
def debug():
    return render_template("debug.html")
