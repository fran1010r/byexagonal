from flask import Flask, render_template, jsonify, request, send_from_directory, redirect, url_for, session, flash, send_file
import os
import json
import zipfile
import io
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esto-en-produccion")

# ── Configuración ──────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
METADATA_FILE = os.path.join(BASE_DIR, "files_metadata.json")
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

def get_tag(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    tags = {
        "pdf": "PDF", "zip": "ZIP", "rar": "ZIP", "7z": "ZIP",
        "jpg": "IMG", "jpeg": "IMG", "png": "IMG", "gif": "IMG", "webp": "IMG",
        "mp4": "VID", "mov": "VID", "avi": "VID", "mkv": "VID",
        "mp3": "AUD", "wav": "AUD", "flac": "AUD",
        "py": "PY", "js": "JS", "html": "HTML", "css": "CSS",
        "xlsx": "XLS", "csv": "CSV", "xls": "XLS",
        "docx": "DOC", "doc": "DOC", "txt": "TXT",
        "pptx": "PPT", "ppt": "PPT",
    }
    return tags.get(ext, ext.upper()[:4] or "FILE")


# ── Rutas públicas ─────────────────────────────────────────────
@app.route("/")
def home():
    files = load_metadata()
    return render_template("index.html", files=files)

@app.route("/download/<filename>")
def download(filename):
    safe_name = secure_filename(filename)
    filepath = os.path.join(UPLOAD_FOLDER, safe_name)

    if not os.path.exists(filepath):
        flash("Archivo no encontrado")
        return redirect(url_for("home"))

    files = load_metadata()
    for f in files:
        if f["filename"] == safe_name:
            f["downloads"] = f.get("downloads", 0) + 1
            break
    save_metadata(files)

    return send_from_directory(UPLOAD_FOLDER, safe_name, as_attachment=True, download_name=safe_name)


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
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    size = os.path.getsize(filepath)
    files = load_metadata()
    files.append({
        "filename": filename,
        "label": label or filename,
        "description": description,
        "size": format_size(size),
        "size_bytes": size,
        "tag": get_tag(filename),
        "date": datetime.now().strftime("%d %b %Y"),
        "downloads": 0
    })
    save_metadata(files)
    flash("Archivo publicado correctamente")
    return redirect(url_for("admin"))

@app.route("/admin/delete/<filename>", methods=["POST"])
def delete_file(filename):
    if not session.get("admin"):
        return redirect(url_for("admin"))

    safe_name = secure_filename(filename)
    filepath = os.path.join(UPLOAD_FOLDER, safe_name)
    if os.path.exists(filepath):
        os.remove(filepath)

    files = [f for f in load_metadata() if f["filename"] != safe_name]
    save_metadata(files)
    flash("Archivo eliminado")
    return redirect(url_for("admin"))


# ── BACKUP ─────────────────────────────────────────────────────
@app.route("/admin/backup")
def backup_download():
    """Genera un ZIP con todos los archivos + metadata y lo descarga."""
    if not session.get("admin"):
        return redirect(url_for("admin"))

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(METADATA_FILE):
            zf.write(METADATA_FILE, "files_metadata.json")

        for fname in os.listdir(UPLOAD_FOLDER):
            if fname == ".gitkeep":
                continue
            fpath = os.path.join(UPLOAD_FOLDER, fname)
            if os.path.isfile(fpath):
                zf.write(fpath, f"uploads/{fname}")

    zip_buffer.seek(0)
    fecha = datetime.now().strftime("%Y%m%d_%H%M%S")

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"backup_exagonal_{fecha}.zip"
    )


# ── RESTORE ────────────────────────────────────────────────────
@app.route("/admin/restore", methods=["POST"])
def backup_restore():
    """Restaura archivos y metadata desde un ZIP de backup."""
    if not session.get("admin"):
        return redirect(url_for("admin"))

    backup_file = request.files.get("backup_zip")
    if not backup_file or backup_file.filename == "":
        flash("No seleccionaste un archivo de backup")
        return redirect(url_for("admin"))

    if not backup_file.filename.endswith(".zip"):
        flash("El archivo debe ser un .zip generado por el backup")
        return redirect(url_for("admin"))

    try:
        zip_buffer = io.BytesIO(backup_file.read())
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            names = zf.namelist()

            if "files_metadata.json" in names:
                with zf.open("files_metadata.json") as mf:
                    metadata = json.load(mf)
                save_metadata(metadata)

            restored = 0
            for name in names:
                if name.startswith("uploads/") and not name.endswith("/"):
                    fname = os.path.basename(name)
                    if fname and fname != ".gitkeep":
                        dest = os.path.join(UPLOAD_FOLDER, fname)
                        with zf.open(name) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
                        restored += 1

        flash(f"Restauración exitosa — {restored} archivo(s) recuperado(s)")
    except Exception as e:
        flash(f"Error al restaurar: {str(e)}")

    return redirect(url_for("admin"))


@app.route("/admin/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/api/status")
def status():
    return jsonify({"status": "online", "project": "By Exagonal", "files": len(load_metadata())})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
