"""Chat UI HTTP server (stdlib-only)."""

import json
import os
import re
import sys
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from . import ollama, tools
from .. import config


def _parse_multipart_file(body: bytes, content_type: str):
    """Parse multipart/form-data body and return (filename, file_bytes) for first file part.
    Works without cgi (removed in Python 3.13). Returns (None, None) if no file found.
    """
    match = re.search(r'boundary=([^;\s]+)', content_type, re.IGNORECASE)
    if not match:
        return None, None
    raw = match.group(1).strip('"').encode()
    boundary = raw if raw.startswith(b'--') else (b'--' + raw)
    # Normalize line endings so we split consistently (Chrome sends \r\n)
    body_norm = body.replace(b'\r\n', b'\n')
    sep = b'\n' + boundary
    parts = body_norm.split(sep)
    for part in parts:
        part = part.strip()
        if not part or part == b'--':
            continue
        if part.startswith(b'--'):
            break
        head, _, rest = part.partition(b'\n\n')
        if not rest:
            continue
        disp = head.decode("utf-8", errors="replace")
        if "filename=" not in disp:
            continue
        name_match = re.search(r'name=["\']?(file|image|reference)["\']?', disp, re.IGNORECASE)
        if not name_match:
            continue
        filename_match = re.search(r'filename=["\']?([^"\'\r\n]*)["\']?', disp, re.IGNORECASE)
        filename = (filename_match.group(1).strip() or "image.png") if filename_match else "image.png"
        # File data is everything before the next boundary (binary-safe)
        idx = rest.find(b'\n' + boundary)
        file_data = rest[:idx].rstrip(b'\n') if idx >= 0 else rest.rstrip(b'\n').rstrip(b'-')
        if file_data:
            return filename, file_data
    return None, None

CHAT_PORT = int(os.environ.get("CHAT_PORT", "8085"))
STATIC_DIR = Path(__file__).parent / "static"


class ChatHandler(BaseHTTPRequestHandler):
    """Handles chat API requests and serves static files."""

    def log_message(self, format, *args):
        print(f"[chat] {args[0]}", file=sys.stderr)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            index = STATIC_DIR / "index.html"
            if index.exists():
                self._send_file(index, "text/html; charset=utf-8")
            else:
                self._send_json({"error": "index.html not found"}, 404)

        elif self.path == "/api/status":
            ollama_status = ollama.check()
            from ..api import check_server
            comfy_status = check_server()
            self._send_json({
                "ollama": ollama_status,
                "comfyui": {"online": comfy_status.get("online", False)},
                "model": ollama.OLLAMA_MODEL,
            })

        elif self.path.startswith("/api/image/"):
            # Serve local output images: /api/image/<relative_path>
            rel = self.path[len("/api/image/"):]
            from .. import config
            # Try images dir then video dir
            for base in [config.IMAGES_DIR, config.VIDEO_DIR, config.OUT_DIR]:
                candidate = base / rel
                if candidate.exists() and candidate.is_file():
                    suffix = candidate.suffix.lower()
                    ct = {
                        ".png": "image/png", ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg", ".webp": "image/webp",
                        ".gif": "image/gif", ".mp4": "video/mp4",
                    }.get(suffix, "application/octet-stream")
                    self._send_file(candidate, ct)
                    return
            self._send_json({"error": "file not found"}, 404)

        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            self._handle_chat(body)
        elif self.path == "/api/upload-reference":
            self._handle_upload_reference()
        else:
            self._send_json({"error": "not found"}, 404)

    def _handle_upload_reference(self):
        """Accept multipart file upload; save to ComfyUI input dir; return filename."""
        try:
            input_dir = config.COMFYUI_INPUT_DIR
            input_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self._send_json({"error": f"Cannot create input dir: {e}"}, 500)
            return

        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self._send_json({"error": "Expected multipart/form-data"}, 400)
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json({"error": "Invalid Content-Length"}, 400)
            return
        if length <= 0 or length > 50 * 1024 * 1024:  # 50 MB max
            self._send_json({"error": "Invalid or too large body"}, 400)
            return

        try:
            body = self.rfile.read(length)
        except Exception as e:
            self._send_json({"error": f"Could not read body: {e}"}, 400)
            return

        filename_orig, file_data = _parse_multipart_file(body, content_type)
        if filename_orig is None or not file_data:
            self._send_json({"error": "No file in form (use field name 'file', 'image', or 'reference')"}, 400)
            return

        ext = Path(filename_orig).suffix.lower() or ".png"
        allowed = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
        if ext not in allowed:
            self._send_json({"error": f"Unsupported type. Use one of: {', '.join(allowed)}"}, 400)
            return

        name = f"comfy_builder_ref_{uuid.uuid4().hex[:12]}{ext}"
        dest = input_dir / name
        try:
            dest.write_bytes(file_data)
        except Exception as e:
            self._send_json({"error": str(e)}, 500)
            return

        self._send_json({"filename": name})

    def _handle_chat(self, body: dict):
        """Process a chat message: call Ollama, execute tools, return result."""
        user_msg = body.get("message", "")
        history = body.get("history", [])
        reference_image = body.get("reference_image")  # filename in ComfyUI input dir

        if not user_msg:
            self._send_json({"error": "empty message"}, 400)
            return

        # If user attached a reference image, append a hint so the LLM can use ref in build_workflow
        if reference_image:
            user_msg = user_msg.rstrip() + f"\n[Reference image attached: {reference_image} — use ref when building. For 'same subject in different poses' use template ref_poses with poses (e.g. standing|sitting). For one image use img2img; for scenes/video use lora_scenes or img2vid.]"

        # Build messages list with system prompt
        messages = [{"role": "system", "content": tools.SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_msg})

        # Send to Ollama with tool definitions
        resp = ollama.chat(messages, tools=tools.TOOL_DEFINITIONS)

        if "error" in resp:
            self._send_json({
                "role": "assistant",
                "content": f"Error contacting Ollama: {resp['error']}",
                "tool_results": [],
            })
            return

        msg = resp.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        tool_results = []

        # Execute tool calls in a loop (LLM may chain multiple)
        max_rounds = 5
        round_num = 0
        while tool_calls and round_num < max_rounds:
            round_num += 1

            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                arguments = fn.get("arguments", {})

                print(f"[chat] Tool call: {name}({json.dumps(arguments, default=str)})",
                      file=sys.stderr)

                # When building a workflow, inject reference image if provided
                if name == "build_workflow" and reference_image and isinstance(arguments, dict):
                    arguments = {**arguments, "ref": reference_image}

                result = tools.execute(name, arguments)
                tool_results.append({
                    "tool": name,
                    "arguments": arguments,
                    "result": result,
                })

                # Add assistant tool_call + tool response to messages
                messages.append(msg)
                messages.append({
                    "role": "tool",
                    "content": json.dumps(result, default=str),
                })

            # Send tool results back to Ollama for next response
            resp = ollama.chat(messages, tools=tools.TOOL_DEFINITIONS)
            if "error" in resp:
                break

            msg = resp.get("message", {})
            tool_calls = msg.get("tool_calls", [])

        content = msg.get("content", "")

        self._send_json({
            "role": "assistant",
            "content": content,
            "tool_results": tool_results,
        })


def main():
    """Start the chat server."""
    print(f"ComfyUI Chat Panel starting on http://localhost:{CHAT_PORT}", file=sys.stderr)
    print(f"  Ollama: {ollama.OLLAMA_URL} (model: {ollama.OLLAMA_MODEL}, timeout: {ollama.OLLAMA_TIMEOUT}s)", file=sys.stderr)
    print(f"  Press Ctrl+C to stop", file=sys.stderr)

    server = HTTPServer(("0.0.0.0", CHAT_PORT), ChatHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", file=sys.stderr)
        server.server_close()
