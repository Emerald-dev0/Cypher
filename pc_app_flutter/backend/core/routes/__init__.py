"""Route blueprints. Registered at the bottom of core.server."""

from __future__ import annotations

from flask import Flask


def register_blueprints(app: Flask) -> None:
    from . import files, guest, media, pairing, recording, system, transfer
    from .bind import rewire_app_views

    for mod in (pairing, files, transfer, system, media, recording, guest):
        app.register_blueprint(mod.bp)
    rewire_app_views(app)
