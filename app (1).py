# JARVIS API bridge — lets Muse ask JARVIS's Gemini backend a question
#
# This does NOT change the Discord bot, its slash commands, or its /ai
# command. The Discord bot can keep running exactly as it is, Gemini-backed.
#
# What this bridge does:
#   Muse -> POST /ask {"question": "..."} -> Gemini -> {"answer": "..."}
#   Muse then posts that answer to Discord itself, using the existing
#   custom.discord connector (which already works for Maja nanbargall...!).
#
# Setup (on the same always-on host as the Discord bot, or any host
# that stays on — Render, Railway, a VPS, a Raspberry Pi):
#   1. Python 3 only — no extra packages needed.
#   2. Set these environment variables, NEVER in this file:
#        GEMINI_API_KEY   — your own Gemini key (Google AI Studio)
#        BRIDGE_API_KEY   — a new secret you invent, just for Muse to
#                           call this bridge. It is NOT your Gemini key
#                           and NOT your Discord bot token.
#   3. Run:  python app.py
#      It listens on port 8000. Expose that port publicly through your
#      host (e.g. Render/Railway gives you a public URL).
#   4. Tell Muse the public host only (never a key in chat). Muse will
#      then create a custom connector for that host, you enter
#      BRIDGE_API_KEY on Muse's secure form, and Muse tests POST /ask.
#
# Security: never paste GEMINI_API_KEY, BRIDGE_API_KEY, or a Discord
# token in chat, in this file, or in a screenshot.

import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer


def gemini_answer(question):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set on the bridge host")
    payload = json.dumps({
        "contents": [{"parts": [{"text": question}]}]
    }).encode("utf-8")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-2.0-flash:generateContent?key=" + key
    )
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini API error {e.code}: {e.read().decode()[:500]}")
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError("Gemini returned an unexpected response")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/ask":
            self._send(404, {"error": "not found"})
            return
        # Muse's bridge key — separate from Gemini and Discord keys.
        bridge_key = os.environ.get("BRIDGE_API_KEY")
        if bridge_key and self.headers.get("X-API-Key") != bridge_key:
            self._send(401, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            question = body["question"]
        except Exception:
            self._send(400, {"error": "send JSON like {\"question\": \"...\"}"})
            return
        try:
            answer = gemini_answer(question)
        except Exception as e:
            self._send(502, {"error": str(e)})
            return
        self._send(200, {"answer": answer})

    def log_message(self, *args):
        # Keep logs free of questions/answers that might contain secrets.
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()
    print(f"JARVIS bridge listening on port {port}")
