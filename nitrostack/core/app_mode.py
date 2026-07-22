import os

def get_app_mode() -> str:
    raw = os.environ.get("NITROSTACK_APP_MODE", "openai").lower().strip()
    if raw in ("mcp-app", "mcpapp", "mcp_app", "mcp app", "mcpapps"):
        return "mcp-app"
    if raw in ("universal", "all", "both"):
        return "universal"
    return "openai"

def is_mcp_app_mode() -> bool:
    mode = get_app_mode()
    return mode in ("mcp-app", "universal")

def is_openai_mode() -> bool:
    mode = get_app_mode()
    return mode in ("openai", "universal")

def get_widget_mime_type() -> str:
    return "text/html;profile=mcp-app" if is_mcp_app_mode() else "text/html"
