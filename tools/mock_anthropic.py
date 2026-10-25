"""Mock da API Anthropic /v1/messages p/ medir o que o Claude Code envia."""
import json
from flask import Flask, Response, request

app = Flask(__name__)


@app.route("/v1/messages", methods=["POST"])
def messages():
    body = request.get_json(silent=True) or {}
    system = body.get("system")
    if isinstance(system, list):
        system = " ".join(b.get("text", "") for b in system if isinstance(b, dict))
    tools = body.get("tools") or []
    with open("/tmp/mock_req.log", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "sys_len": len(system or ""), "n_msgs": len(body.get("messages", [])),
            "model": body.get("model"),
            "tools_n": len(tools), "tools_len": len(json.dumps(tools)),
            "tools": [x.get("name") for x in tools],
        }) + "\n")
    if not body.get("stream"):
        return Response(json.dumps({
            "id": "msg_mock", "type": "message", "role": "assistant",
            "model": body.get("model", "mock"),
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 10, "output_tokens": 7},
        }), mimetype="application/json")

    def sse():
        yield 'event: message_start\ndata: ' + json.dumps({"type": "message_start", "message": {"id": "m", "type": "message", "role": "assistant", "content": [], "model": body.get("model", "m"), "stop_reason": None, "usage": {"input_tokens": 10, "output_tokens": 0}}}) + "\n\n"
        yield 'event: content_block_start\ndata: ' + json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}) + "\n\n"
        yield 'event: content_block_delta\ndata: ' + json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ok"}}) + "\n\n"
        yield 'event: content_block_stop\ndata: ' + json.dumps({"type": "content_block_stop", "index": 0}) + "\n\n"
        yield 'event: message_delta\ndata: ' + json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": 2}}) + "\n\n"
        yield 'event: message_stop\ndata: ' + json.dumps({"type": "message_stop"}) + "\n\n"
    return Response(sse(), mimetype="text/event-stream")


@app.route("/v1/messages/count_tokens", methods=["POST"])
def count_tokens():
    return Response(json.dumps({"input_tokens": 42}), mimetype="application/json")


@app.route("/v1/models", methods=["GET"])
def models():
    return Response(json.dumps({"data": [{"id": "qwen2.5-coder:7b"}]}), mimetype="application/json")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8140, threaded=True)
