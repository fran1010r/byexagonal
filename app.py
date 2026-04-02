from flask import Flask, render_template, jsonify, request, send_from_directory, redirect, url_for, session, flash
import os
import json
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esto-en-produccion")

# ── Configuración ──────────────────────────────────────────────
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
METADATA_FILE = os.path.join(os.path.dirname(__file__), "files_metadata.json")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────
def load_metadata():
    if not os.path.exists(METADATA_FILE):
        return []
    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_metadata(data):
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def format_size(bytes):
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} TB"

def get_icon(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    icons = {
        "pdf": "PDF", "zip": "ZIP", "rar": "ZIP", "7z": "ZIP",
        "jpg": "IMG", "jpeg": "IMG", "png": "IMG", "gif": "IMG", "webp": "IMG",
        "mp4": "VID", "mov": "VID", "avi": "VID", "mkv": "VID",
        "mp3": "AUD", "wav": "AUD", "flac": "AUD",
        "py": "PY", "js": "JS", "html": "HTML", "css": "CSS",
        "xlsx": "XLS", "csv": "CSV", "xls": "XLS",
        "docx": "DOC", "doc": "DOC", "txt": "TXT",
        "pptx": "PPT", "ppt": "PPT",
    }
    return icons.get(ext, ext.upper()[:3] or "FILE")


# ── Rutas públicas ─────────────────────────────────────────────
@app.route("/")
def home():
    files = load_metadata()
    return render_template("index.html", files=files)

@app.route("/download/<filename>")
def download(filename):
    safe_name = secure_filename(filename)
    files = load_metadata()
    for f in files:
        if f["filename"] == safe_name:
            f["downloads"] = f.get("downloads", 0) + 1
            break
    save_metadata(files)
    return send_from_directory(app.config["UPLOAD_FOLDER"], safe_name, as_attachment=True)


# ── Admin ──────────────────────────────────────────────────────
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST" and "password" in request.form:
        if request.form["password"] == ADMIN_PASSWORD:
            session["admin"] = True
        else:
            flash("Contraseña incorrecta")
        return redirect(url_for("admin"))

    if not session.get("admin"):
        return render_template("login.html")

    files = load_metadata()
    return render_template("admin.html", files=files)

@app.route("/admin/upload", methods=["POST"])
def upload():
    if not session.get("admin"):
        return redirect(url_for("admin"))

    file = request.files.get("file")
    label = request.form.get("label", "").strip()
    description = request.form.get("description", "").strip()

    if not file or file.filename == "":
        flash("No seleccionaste ningún archivo")
        return redirect(url_for("admin"))

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    size = os.path.getsize(filepath)
    files = load_metadata()
    files.append({
        "filename": filename,
        "label": label or filename,
        "description": description,
        "size": format_size(size),
        "size_bytes": size,
        "tag": get_icon(filename),
        "date": datetime.now().strftime("%d %b %Y"),
        "downloads": 0
    })
    save_metadata(files)
    flash(f"Archivo publicado correctamente")
    return redirect(url_for("admin"))

@app.route("/admin/delete/<filename>", methods=["POST"])
def delete_file(filename):
    if not session.get("admin"):
        return redirect(url_for("admin"))

    safe_name = secure_filename(filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    if os.path.exists(filepath):
        os.remove(filepath)

    files = load_metadata()
    files = [f for f in files if f["filename"] != safe_name]
    save_metadata(files)
    flash("Archivo eliminado")
    return redirect(url_for("admin"))

@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/api/status")
def status():
    return jsonify({"status": "online", "files": len(load_metadata())})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
