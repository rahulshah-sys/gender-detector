"""
app.py
------
Tiny Flask API for the name-based gender detector.

Endpoints:
  GET  /            -> simple status page (so the HF Space "preview" isn't blank)
  GET  /health      -> health check (use this from Apps Script to confirm the
                        Space is awake before sending a big batch)
  POST /predict      -> single name:   {"username": "...", "full_name": "..."}
  POST /predict_batch -> multiple rows: {"rows": [{"username":..,"full_name":..}, ...]}
                        (use this from Apps Script instead of one HTTP call per
                        row - this is what avoids the Gunicorn timeout / 500s
                        you ran into on the DeepFace Space when sending too many
                        tiny requests back-to-back)
"""

from flask import Flask, jsonify, request

from gender_detector import predict

app = Flask(__name__)

MAX_BATCH_SIZE = 200  # keep batches small & fast; tune after you see real timings


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "service": "name-gender-detector"})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/predict", methods=["POST"])
def predict_single():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "") or ""
    full_name = data.get("full_name", "") or ""

    if not username and not full_name:
        return jsonify({"error": "Send 'username' and/or 'full_name'"}), 400

    result = predict(username=username, full_name=full_name)
    return jsonify(result)


@app.route("/predict_batch", methods=["POST"])
def predict_batch():
    data = request.get_json(silent=True) or {}
    rows = data.get("rows", [])

    if not isinstance(rows, list) or not rows:
        return jsonify({"error": "Send 'rows': [{'username':..,'full_name':..}, ...]"}), 400

    if len(rows) > MAX_BATCH_SIZE:
        return jsonify({"error": f"Max {MAX_BATCH_SIZE} rows per batch"}), 400

    results = []
    for row in rows:
        username = row.get("username", "") or ""
        full_name = row.get("full_name", "") or ""
        results.append(predict(username=username, full_name=full_name))

    return jsonify({"results": results})


if __name__ == "__main__":
    # local dev only - HF Space uses gunicorn (see Dockerfile)
    app.run(host="0.0.0.0", port=7860, debug=True)
