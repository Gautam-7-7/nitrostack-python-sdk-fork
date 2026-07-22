import os
import subprocess
import sys
import re

def compile_next_widget(project_dir: str, route_path: str) -> str:
    """
    Statically compiles a Next.js directory into a single HTML bundle
    with CSS and JS fully inlined (Section 17).
    """
    abs_project_dir = os.path.abspath(project_dir)
    
    node_modules_path = os.path.join(abs_project_dir, "node_modules")
    env = os.environ.copy()
    env["NODE_ENV"] = "production"
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    
    if not os.path.exists(node_modules_path):
        sys.stderr.write(f"Installing npm dependencies in {abs_project_dir}...\n")
        sys.stderr.flush()
        # npm install with --no-audit and --no-fund is faster
        subprocess.run("npm install --no-audit --no-fund", cwd=abs_project_dir, shell=True, env=env, check=True)
        
    # Build next.js project statically if out directory does not exist or is empty
    out_dir = os.path.join(abs_project_dir, "out")
    if not os.path.exists(out_dir) or not os.listdir(out_dir) or os.environ.get("FORCE_BUILD") == "true":
        sys.stderr.write(f"Building Next.js widget at {abs_project_dir}...\n")
        sys.stderr.flush()
        subprocess.run("npm run build", cwd=abs_project_dir, shell=True, env=env, check=True)
    if not os.path.exists(out_dir):
        raise FileNotFoundError(f"Static build output directory not found at {out_dir}")
        
    # Try different output HTML paths for the specified route
    html_paths = [
        os.path.join(out_dir, f"{route_path}.html"),
        os.path.join(out_dir, route_path, "index.html"),
        os.path.join(out_dir, "index.html")
    ]
    
    html_path = None
    for path in html_paths:
        if os.path.exists(path):
            html_path = path
            break
            
    if not html_path:
        raise FileNotFoundError(
            f"Could not locate static HTML file for route '{route_path}' in build output {out_dir}"
        )
        
    # Read HTML content
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    # 1. Inline CSS stylesheets
    def replace_link(match):
        link_tag = match.group(0)
        # Verify it is a stylesheet
        if not re.search(r'\brel=["\']stylesheet["\']', link_tag, re.IGNORECASE):
            return link_tag
            
        href_match = re.search(r'\bhref=["\']([^"\']+)["\']', link_tag, re.IGNORECASE)
        if not href_match:
            return link_tag
            
        href = href_match.group(1)
        if href.startswith(("http://", "https://", "//")):
            return link_tag
            
        relative_href = href.lstrip("/")
        css_file_path = os.path.join(out_dir, relative_href)
        if os.path.exists(css_file_path):
            with open(css_file_path, "r", encoding="utf-8") as css_f:
                css_content = css_f.read()
            return f"<style>{css_content}</style>"
        return link_tag

    html_content = re.sub(r'<link\b[^>]+>', replace_link, html_content, flags=re.IGNORECASE)
    
    # 2. Inline JS scripts
    def replace_script(match):
        script_tag = match.group(0)
        src_match = re.search(r'\bsrc=["\']([^"\']+)["\']', script_tag, re.IGNORECASE)
        if not src_match:
            return script_tag
            
        src = src_match.group(1)
        if src.startswith(("http://", "https://", "//")):
            return script_tag
            
        relative_src = src.lstrip("/")
        js_file_path = os.path.join(out_dir, relative_src)
        if os.path.exists(js_file_path):
            with open(js_file_path, "r", encoding="utf-8") as js_f:
                js_content = js_f.read()
            # Prevent HTML breaking on closing script tags inside JS strings
            js_content_escaped = js_content.replace("</script>", "<\\/script>")
            return f"<script>{js_content_escaped}</script>"
        return script_tag

    html_content = re.sub(r'<script\b[^>]+>\s*</script>', replace_script, html_content, flags=re.IGNORECASE)
    
    return html_content
