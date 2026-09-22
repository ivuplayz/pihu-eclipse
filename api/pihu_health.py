"""Cloud health endpoint for Pihu-BreakThough.

This endpoint is intentionally small: it verifies that the Vercel Python
runtime can import Pihu's core and, when configured, reach Neon PostgreSQL.
"""
import os

from flask import jsonify

from pihu_core.router import PihuRouter

def handler(request):
    db_ok = False
    db_error = None
    database_url = os.getenv("DATABASE_URL", "").strip()

    if database_url:
        try:
            import psycopg
            with psycopg.connect(database_url, connect_timeout=5) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
            db_ok = True
        except Exception as exc:
            db_error = str(exc)

    router = PihuRouter()
    return jsonify({
        "ok": True,
        "app": "Pihu-BreakThough",
        "runtime": "vercel",
        "database": {
            "configured": bool(database_url),
            "reachable": db_ok,
            "error": db_error,
        },
        "capabilities": router.capabilities(),
    })
