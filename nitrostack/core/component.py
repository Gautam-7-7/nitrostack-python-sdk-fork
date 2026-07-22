import os
import sys
from typing import Any, Callable, Dict, Optional
from nitrostack.core.app_mode import get_widget_mime_type

class Component:
    def __init__(self, definition: Dict[str, Any]):
        self.definition = definition
        self.compiled = False
        self.bundle: Dict[str, str] = {"html": ""}
        self.validate_definition()

    def validate_definition(self) -> None:
        if not self.definition.get("id"):
            raise ValueError("Component ID is required")
        if not self.definition.get("name"):
            raise ValueError("Component name is required")

    @property
    def id(self) -> str:
        return self.definition["id"]

    @property
    def name(self) -> str:
        return self.definition["name"]

    @property
    def description(self) -> Optional[str]:
        return self.definition.get("description")

    async def compile(self) -> None:
        if self.compiled:
            return

        widgets_out_dir = os.path.abspath(os.path.join(os.getcwd(), "src", "widgets", "out"))
        component_html_path = os.path.join(widgets_out_dir, f"{self.id}.html")

        if not os.path.exists(component_html_path) and self.id.startswith("next-"):
            id_without_prefix = self.id[5:]
            component_html_path = os.path.join(widgets_out_dir, f"{id_without_prefix}.html")

        if os.path.exists(component_html_path):
            try:
                with open(component_html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                self.bundle = {"html": html_content}
                self.compiled = True
                return
            except Exception as e:
                sys.stderr.write(f"Warning: Failed to read widget file for {self.id}: {e}\n")

        self.bundle = {
            "html": self.definition.get("html") or "",
            "css": self.definition.get("css") or "",
            "js": self.definition.get("js") or "",
        }
        self.compiled = True

    def get_bundle(self) -> str:
        if not self.compiled:
            raise RuntimeError("Component not compiled. Call compile() first.")
        css_tag = f"<style>{self.bundle['css']}</style>" if self.bundle.get("css") else ""
        js_tag = f"<script type=\"module\">{self.bundle['js']}</script>" if self.bundle.get("js") else ""
        return f"{self.bundle['html']}\n{css_tag}\n{js_tag}".strip()

    def get_resource_uri(self) -> str:
        meta = self.definition.get("_meta", {})
        if meta.get("devMode") and meta.get("devUrl"):
            return str(meta["devUrl"])
        return f"ui://widget/{self.id}.html"

    def is_dev_mode(self) -> bool:
        return bool(self.definition.get("_meta", {}).get("devMode"))

    def get_dev_url(self) -> Optional[str]:
        return self.definition.get("_meta", {}).get("devUrl")

    async def transform_data(self, data: Any, context: Any) -> Any:
        transformer = self.definition.get("transformer")
        if transformer:
            if inspect.iscoroutinefunction(transformer):
                return await transformer(data, context)
            else:
                return transformer(data, context)
        return data

    async def get_widget_meta(self, data: Any, context: Any) -> Any:
        meta_transformer = self.definition.get("meta_transformer") or self.definition.get("metaTransformer")
        if meta_transformer:
            import inspect
            if inspect.iscoroutinefunction(meta_transformer):
                return await meta_transformer(data, context)
            else:
                return meta_transformer(data, context)
        return None

    async def initialize(self, context: Any) -> None:
        on_init = self.definition.get("on_init") or self.definition.get("onInit")
        if on_init:
            import inspect
            import asyncio
            if inspect.iscoroutinefunction(on_init):
                await on_init(context)
            else:
                await asyncio.to_thread(on_init, context)


    def get_provider_metadata(self, provider: str = "openai") -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        if provider == "openai":
            metadata["openai/outputTemplate"] = self.get_resource_uri()
            metadata["openai/widgetAccessible"] = self.definition.get("canInvokeTools", False)
            if self.description:
                metadata["openai/widgetDescription"] = self.description
            if self.definition.get("prefersBorder"):
                metadata["openai/widgetPrefersBorder"] = True
            if self.definition.get("subdomain"):
                metadata["openai/widgetDomain"] = self.definition.get("subdomain")
            csp = self.definition.get("csp")
            if csp and isinstance(csp, dict):
                csp_meta = {}
                if csp.get("connectDomains"):
                    csp_meta["connect_domains"] = csp["connectDomains"]
                if csp.get("resourceDomains"):
                    csp_meta["resource_domains"] = csp["resourceDomains"]
                if csp.get("frameDomains"):
                    csp_meta["frame_domains"] = csp["frameDomains"]
                if csp_meta:
                    metadata["openai/widgetCSP"] = csp_meta
        elif provider == "anthropic":
            metadata["anthropic/ui"] = self.get_resource_uri()
        else:
            metadata["ui/template"] = self.get_resource_uri()
            metadata["ui/interactive"] = self.definition.get("canInvokeTools", False)

        provider_meta = self.definition.get("providerMetadata")
        if provider_meta and isinstance(provider_meta, dict):
            metadata.update(provider_meta)
        return metadata

    def get_resource_metadata(self) -> Dict[str, Any]:
        metadata = {
            "mimeType": "text/html"
        }
        openai_meta = self.get_provider_metadata("openai")
        for key in ("openai/widgetCSP", "openai/widgetDescription", "openai/widgetPrefersBorder", "openai/widgetDomain"):
            if key in openai_meta:
                metadata[key] = openai_meta[key]
        return metadata

def create_component(definition: Dict[str, Any]) -> Component:
    return Component(definition)

def create_component_from_next_route(route_path: str, options: Optional[Dict[str, Any]] = None) -> Component:
    options = options or {}
    widgets_dev_mode = os.environ.get("WIDGETS_DEV_MODE") == "true"
    cid = options.get("id") or f"next-{route_path}"
    cname = options.get("name") or " ".join(s.capitalize() for s in route_path.split("-"))

    if widgets_dev_mode:
        return create_component({
            "id": cid,
            "name": cname,
            "description": options.get("description"),
            "html": f"<!-- Widget loaded from dev server: /widgets/{route_path} -->",
            "prefersBorder": options.get("prefersBorder"),
            "subdomain": options.get("subdomain") or options.get("domain"),
            "csp": options.get("csp"),
            "transformer": options.get("transformer"),
            "_meta": {
                "devUrl": f"/widgets/{route_path}",
                "devMode": True
            }
        })

    # Non dev-mode static loading options
    src_widgets_root = os.path.abspath(os.path.join(os.getcwd(), "src", "widgets"))
    dist_widgets_root = os.path.abspath(os.path.join(os.getcwd(), "dist", "widgets"))
    project_dir = options.get("projectDir") or (src_widgets_root if os.path.exists(src_widgets_root) else dist_widgets_root)

    return create_component({
        "id": cid,
        "name": cname,
        "description": options.get("description"),
        "projectDir": project_dir,
        "prefersBorder": options.get("prefersBorder"),
        "subdomain": options.get("subdomain") or options.get("domain"),
        "csp": options.get("csp"),
        "transformer": options.get("transformer"),
    })
