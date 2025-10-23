import os
import subprocess
import shutil
import uuid
from bs4 import BeautifulSoup
from urllib.parse import unquote

# -------- CONFIG --------
SEVEN_ZIP_CMD = r"C:\Program Files\7-Zip\7z.exe"  # adjust path
SKIP_IMAGES = {"ccslogo.png", "plplogo.png"}


def decode_chm_path(path: str) -> str:
    """Decode CHM internal paths safely (handles %20 and encoding)."""
    path = unquote(path)
    try:
        path = path.encode("latin1").decode("utf-8")
    except Exception:
        pass
    return path


def cleanup_keep_merged_and_images(output_dir: str, merged_file="merged.html", images_folder="Images"):
    """Remove everything except merged.html and Images/."""
    for item in os.listdir(output_dir):
        item_path = os.path.join(output_dir, item)
        if item in (merged_file, images_folder):
            continue
        if os.path.isfile(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)
    print(f"[+] Cleanup done. Kept {merged_file} and {images_folder}/ folder.")


def extract_chm(chm_path: str, output_dir: str):
    """Extract CHM using 7-Zip."""
    os.makedirs(output_dir, exist_ok=True)
    print(f"[*] Extracting {chm_path} → {output_dir}")
    subprocess.run([SEVEN_ZIP_CMD, "x", chm_path, f"-o{output_dir}"], check=True)
    print("[+] Extraction complete.")


def fix_html_paths(output_dir: str):
    """Normalize backslashes and remove hhctrl:// references."""
    for root, _, files in os.walk(output_dir):
        for fname in files:
            if fname.lower().endswith((".htm", ".html")):
                path = os.path.join(root, fname)
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    html = f.read()
                html = html.replace("\\", "/").replace("hhctrl://", "")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
    print("[+] Fixed HTML paths.")


def parse_toc(output_dir: str):
    """Parse Table of Contents (.hhc) to get ordered HTML files."""
    hhc_file = os.path.join(output_dir, "Table of Contents.hhc")
    toc_files = []
    if os.path.exists(hhc_file):
        with open(hhc_file, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f, "html.parser")
        for obj in soup.find_all("object", type="text/sitemap"):
            local_param = obj.find("param", attrs={"name": "Local"})
            name_param = obj.find("param", attrs={"name": "Name"})
            if not local_param:
                continue
            rel_path = decode_chm_path(local_param.get("value", "").strip())
            abs_path = os.path.join(output_dir, rel_path)
            if os.path.exists(abs_path):
                title = name_param.get("value") if name_param else os.path.basename(rel_path)
                toc_files.append((abs_path, title))

    # fallback: all html files
    if not toc_files:
        print("[!] TOC missing — falling back to all HTML files alphabetically.")
        for root, _, files in os.walk(output_dir):
            for f in files:
                if f.lower().endswith((".htm", ".html")):
                    toc_files.append((os.path.join(root, f), f))
        toc_files.sort(key=lambda x: (len(x[0]), x[0].lower()))

    print(f"[+] Found {len(toc_files)} pages.")
    return toc_files


def merge_html(toc_files, output_dir):
    """Merge all HTML pages into one with sidebar + dark mode."""
    merged_file = os.path.join(output_dir, "merged.html")
    html_parts = [
        "<!DOCTYPE html>",
        "<html><head><meta charset='utf-8'><title>Merged CHM</title>",
        """<style>
        body { font-family:sans-serif; margin:0; padding:0; display:flex; transition:background .3s,color .3s; }
        #sidebar { width:220px; background:#f4f4f4; padding:20px; height:100vh; overflow:auto; position:sticky; top:0; }
        #content { flex:1; padding:20px; max-width:900px; margin:auto; line-height:1.6; }
        #content p { text-indent:2em; margin-top:0.5em; margin-bottom:0.5em; }
        #content img { max-width:100%; height:auto; margin:10px 0; }
        #sidebar a { display:block; margin:6px 0; color:#333; text-decoration:none; }
        #sidebar a:hover { text-decoration:underline; }
        h2 { margin-top:40px; }
        .dark body, .dark #content { background:#1e1e1e; color:#ddd; }
        .dark #sidebar { background:#2b2b2b; color:#ddd; }
        .dark #sidebar a { color:#ccc; }
        #toggle-darkmode { position:fixed; top:10px; right:10px; background:#333; color:#fff;
                           border:none; padding:8px 12px; border-radius:6px; cursor:pointer; }
        #toggle-darkmode:hover { background:#555; }
        </style></head><body>
        <button id="toggle-darkmode">Toggle Dark Mode</button>
        <div id="sidebar"><ul>"""
    ]

    # Sidebar links
    for idx, (_, title) in enumerate(toc_files):
        html_parts.append(f'<li><a href="#section-{idx}">{title}</a></li>')
    html_parts.append("</ul></div><div id='content'>")

    # Page content
    for idx, (fpath, title) in enumerate(toc_files):
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f, "html.parser")

        # cleanup
        for tag in soup.select("div.hd, div.footer"):
            tag.decompose()
        for img in soup.find_all("img", src=True):
            img_filename = os.path.basename(img["src"]).lower()
            if img_filename in SKIP_IMAGES:
                img.decompose()
                continue
            img["src"] = f"Images/{img_filename}".replace("\\", "/")
            img["style"] = "max-width:100%;height:auto;display:block;margin:10px 0;"

        html_parts.append(f"<h2 id='section-{idx}'>{title}</h2>")
        html_parts.append(str(soup.body or soup))

    html_parts.append("""</div>
    <script>
    const btn = document.getElementById('toggle-darkmode');
    btn.addEventListener('click', () => {
        document.documentElement.classList.toggle('dark');
        btn.textContent = document.documentElement.classList.contains('dark')
            ? 'Light Mode' : 'Dark Mode';
    });
    </script></body></html>""")

    with open(merged_file, "w", encoding="utf-8") as f:
        f.write("\n".join(html_parts))

    print(f"[+] Merged HTML created → {merged_file}")
    return merged_file


def merge_chm_to_html(chm_path: str, media_root="."):
    """Full pipeline: extract → fix paths → parse TOC → merge → cleanup."""
    unique_id = str(uuid.uuid4())[:8]
    output_dir = os.path.join(media_root, f"chm_{unique_id}")
    merged_file = os.path.join(output_dir, "merged.html")

    extract_chm(chm_path, output_dir)
    fix_html_paths(output_dir)
    toc_files = parse_toc(output_dir)
    merge_html(toc_files, output_dir)
    cleanup_keep_merged_and_images(output_dir)

    print("[INFO] Done. Open merged.html in your browser.")
    return merged_file, output_dir



