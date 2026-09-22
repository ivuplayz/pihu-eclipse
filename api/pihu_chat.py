"""Minimal Vercel chat endpoint for Pihu-BreakThough."""
import json

from flask import Response, request

from pihu_core.router import PihuRouter

router = PihuRouter()

def _response(payload, status=200):
    return Response(json.dumps(payload), status=status, mimetype="application/json")

def handler(req):
    if req.method != "POST":
        return _response({"ok": False, "error": "Use POST"}, 405)

    body = request.get_json(silent=True) or {}
    message = str(body.get("message", "")).strip()

    if not message:
        return _response({"ok": False, "error": "message is required"}, 400)

    result = router.chat([
        {
            "role": "system",
            "content": (
                "You are Pihu-BreakThough, a personal AI assistant. "
                "Be natural, helpful, concise, and adapt to the user's language."
            ),
        },
        {"role": "user", "content": message},
    ])

    if not result.ok:
        return _response({
            "ok": False,
            "error": result.error,
            "provider": result.provider,
        }, 503)

    return _response({
        "ok": True,
        "answer": result.text,
        "provider": result.provider,
    })
