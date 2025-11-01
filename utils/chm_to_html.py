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
    except:
        pass
    return path


def cleanup_keep_merged_and_images(output_dir: str, merged_file="merged.html", images_folder="Images"):
    """Remove everything except merged.html and Images/."""
    for item in os.listdir(output_dir):
        item_path = os.path.join(output_dir, item)
        if item == merged_file or item == images_folder:
            continue
        if os.path.isfile(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)
    print(f"[+] Cleanup done. Kept {merged_file} and {images_folder}/ folder.")


def extract_chm(chm_path: str, output_dir: str):
    """Extract CHM using 7-Zip."""
    try:
        subprocess.run([SEVEN_ZIP_CMD, "x", chm_path, f"-o{output_dir}"], check=True)
        print(f"[+] Extracted CHM to {output_dir}")
    except subprocess.CalledProcessError:
        print("[!] Failed to extract CHM.")
        exit(1)


def fix_html_paths(output_dir: str):
    """Normalize backslashes and remove hhctrl:// references."""
    for root, dirs, files in os.walk(output_dir):
        for fname in files:
            if fname.lower().endswith((".htm", ".html")):
                path = os.path.join(root, fname)
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    html = f.read()
                html = html.replace("\\", "/").replace("hhctrl://", "")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(html)
    print("[+] HTML paths fixed.")


def parse_toc(output_dir: str):
    """Parse Table of Contents (.hhc) to get ordered HTML files."""
    hhc_file = os.path.join(output_dir, "Table of Contents.hhc")
    toc_files = []

    if os.path.exists(hhc_file):
        with open(hhc_file, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f, "html.parser")
            objects = soup.find_all("object", type="text/sitemap")
            for obj in objects:
                local_param = obj.find("param", attrs={"name": "Local"})
                name_param = obj.find("param", attrs={"name": "Name"})
                if local_param:
                    rel_path = decode_chm_path(local_param.get("value", "").strip())
                    abs_path = os.path.join(output_dir, rel_path)
                    if os.path.exists(abs_path):
                        title = name_param.get("value") if name_param else os.path.basename(rel_path)
                        toc_files.append((abs_path, title))

    if not toc_files:
        print("[!] TOC parse failed or empty, merging all HTML files alphabetically.")
        for root, dirs, files in os.walk(output_dir):
            for f in files:
                if f.lower().endswith((".htm", ".html")):
                    toc_files.append((os.path.join(root, f), f))
        toc_files.sort(key=lambda x: (len(x[0]), x[0].lower()))

    print(f"[+] {len(toc_files)} pages to merge.")
    return toc_files


def merge_html(toc_files, output_dir):
    """Merge all HTML pages into one with sidebar + dark mode."""
    merged_file = os.path.join(output_dir, "merged.html")

    merged_content = """<!DOCTYPE html>
<html>
<head>
  <meta charset='utf-8'>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Merged CHM</title>
<style>
body {
  font-family: sans-serif;
  margin: 0;
  padding: 0;
  display: flex;
  transition: background 0.3s, color 0.3s;
}
#sidebar {
  width: 200px;
  background: #f4f4f4;
  padding: 20px;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: auto;
  transition: background 0.3s, color 0.3s;
}
#content {
  flex: 1;
  padding: 20px;
  max-width: 800px;
  margin: auto;
  line-height: 1.5;
  transition: background 0.3s, color 0.3s;
}
#content p {
  text-indent: 2em;
  margin-top: 0.5em;
  margin-bottom: 0.5em;
}
#content img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 10px 0;
}
#sidebar a {
  display: block;
  margin-bottom: 8px;
  color: #333;
  text-decoration: none;
}
#sidebar a:hover {
  text-decoration: underline;
}
h2 {
  margin-top: 40px;
}
.dark body {
  background: #1e1e1e;
  color: #ddd;
}
.dark #sidebar {
  background: #2b2b2b;
  color: #ddd;
  scrollbar-color: rgb(45, 44, 44) rgb(94, 93, 93);  
}
.dark #sidebar a {
  color: #ddd;
}
.dark #sidebar a:hover {
  color: #fff;
}
.dark #content {
  background: #1e1e1e;
  color: #ddd;
}
#toggle-darkmode {
  position: fixed;
  top: 10px;
  right: 10px;
  background: #333;
  color: white;
  border: none;
  padding: 8px 12px;
  border-radius: 5px;
  cursor: pointer;
}
#toggle-darkmode:hover {
  background: #555;
}
</style>
</head>
<body>
<button id="toggle-darkmode">Toggle Dark Mode</button>
<div id="sidebar">
<ul>
"""

    # Sidebar links
    for idx, (_, title) in enumerate(toc_files):
        merged_content += f'<li><a href="#section-{idx}">{title}</a></li>\n'

    merged_content += "</ul>\n</div>\n<div id='content'>\n"

    # Page content
    for idx, (fpath, title) in enumerate(toc_files):
        safe_id = f"section-{idx}"
        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
            page_soup = BeautifulSoup(f, "html.parser")

        for hd_div in page_soup.find_all("div", class_="hd"):
            hd_div.decompose()
        footer = page_soup.find("div", class_="footer")
        if footer:
            footer.decompose()

        for link in page_soup.find_all("link", href=True):
            link['href'] = os.path.join(os.path.dirname(fpath), link['href']).replace("\\", "/")

        for img in page_soup.find_all("img", src=True):
            img_filename = os.path.basename(img['src']).lower()
            if img_filename in SKIP_IMAGES:
                img.decompose()
                continue
            img['src'] = f"Images/{img_filename}".replace("\\", "/")
            img['style'] = "max-width:100%; height:auto; display:block; margin:10px 0;"

        body = page_soup.body
        if body:
            merged_content += f"<h2 id='{safe_id}' style='visibility:hidden; height:0; margin:0; padding:0;'>{title}</h2>\n"
            merged_content += str(body) + "\n"
        else:
            merged_content += str(page_soup) + "\n"

    merged_content += """
</div>
<script>
const btn = document.getElementById('toggle-darkmode');
btn.addEventListener('click', () => {
  document.documentElement.classList.toggle('dark');
  btn.textContent = document.documentElement.classList.contains('dark')
    ? 'Light Mode'
    : 'Dark Mode';
});
</script>
</body>
</html>
"""

    with open(merged_file, "w", encoding="utf-8") as f:
        f.write(merged_content)

    print(f"[+] Merged HTML created: {merged_file}")
    return merged_file


def merge_chm_to_html(chm_path: str, media_root="."):
    """Full pipeline: extract → fix paths → parse TOC → merge → cleanup."""
    unique_id = str(uuid.uuid4())[:8]
    output_dir = os.path.join(media_root, f"chm_{unique_id}")

    extract_chm(chm_path, output_dir)
    fix_html_paths(output_dir)
    toc_files = parse_toc(output_dir)
    merge_html(toc_files, output_dir)
    cleanup_keep_merged_and_images(output_dir)

    print("[INFO] Done. Open merged.html in your browser.")
    return os.path.join(output_dir, "merged.html"), output_dir
