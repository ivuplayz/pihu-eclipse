"""Minimal Vercel chat endpoint for Pihu-BreakThough."""
from flask import jsonify, request

from pihu_core.router import PihuRouter

router = PihuRouter()

def handler(req):
    if req.method != "POST":
        return jsonify({"ok": False, "error": "Use POST"}), 405

    body = req.get_json(silent=True) or {}
    message = str(body.get("message", "")).strip()

    if not message:
        return jsonify({"ok": False, "error": "message is required"}), 400

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
        return jsonify({
            "ok": False,
            "error": result.error,
            "provider": result.provider,
        }), 503

    return jsonify({
        "ok": True,
        "answer": result.text,
        "provider": result.provider,
    })
