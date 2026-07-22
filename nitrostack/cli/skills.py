import os
import sys
import shutil
import tempfile
import json
import subprocess
from typing import List, Dict, Any, Optional

SKILLS_REPO_URL = "https://github.com/nitrocloudofficial/skills.git"

class AgentDescriptor:
    def __init__(self, agent_id: str, name: str, folder_name: str, cmd: Optional[str] = None, get_skills_dir: Optional[Any] = None):
        self.id = agent_id
        self.name = name
        self.folder_name = folder_name
        self.cmd = cmd
        self._get_skills_dir = get_skills_dir

    def detect(self) -> bool:
        # Check command exists
        if self.cmd:
            which_cmd = "where" if sys.platform == "win32" else "which"
            try:
                subprocess.run([which_cmd, self.cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                return True
            except Exception:
                pass
        # Check folder exists
        home = os.path.expanduser("~")
        return os.path.isdir(os.path.join(home, self.folder_name))

    def get_skills_dir(self, scope: str = "global", project_dir: str = None) -> str:
        if self._get_skills_dir:
            return self._get_skills_dir(scope, project_dir)
        base = project_dir if scope == "project" else os.path.expanduser("~")
        return os.path.join(base, self.folder_name, "skills")

def get_opencode_skills_dir(scope: str = "global", project_dir: str = None) -> str:
    if scope == "project":
        return os.path.join(project_dir, ".opencode", "skills")
    return os.path.join(os.path.expanduser("~"), ".config", "opencode", "skills")

AGENTS = [
    AgentDescriptor("cursor", "Cursor Agent", ".cursor"),
    AgentDescriptor("codex", "Codex", ".codex", cmd="codex"),
    AgentDescriptor("claude-code", "Claude Code", ".claude", cmd="claude"),
    AgentDescriptor("gemini-cli", "Gemini CLI", ".gemini", cmd="gemini"),
    AgentDescriptor("antigravity", "Google Antigravity", ".antigravity", cmd="agy"),
    AgentDescriptor("github-copilot", "GitHub Copilot Agent", ".copilot"),
    AgentDescriptor("opencode", "OpenCode Agent", ".config/opencode", cmd="opencode", get_skills_dir=get_opencode_skills_dir),
    AgentDescriptor("agents", "Workspace Agents", ".agents"),
]

def clone_skills_repo() -> str:
    temp_dir = tempfile.mkdtemp(prefix="nitrostack-skills-")
    try:
        subprocess.run(["git", "clone", "--depth", "1", SKILLS_REPO_URL, temp_dir], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return temp_dir
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise RuntimeError(f"Failed to clone skills repository: {e}")

def discover_skills(clone_dir: str) -> List[Dict[str, str]]:
    skills_dir = os.path.join(clone_dir, "skills")
    if not os.path.isdir(skills_dir):
        return []
    skills = []
    for entry in os.listdir(skills_dir):
        if entry.startswith("."):
            continue
        entry_path = os.path.join(skills_dir, entry)
        if os.path.isdir(entry_path):
            skills.append({"name": entry, "path": entry_path})
    skills.sort(key=lambda s: s["name"])
    return skills

def install_skills(agents: List[AgentDescriptor], skills: List[Dict[str, str]], force: bool = False, scope: str = "global", project_dir: str = None) -> List[Dict[str, Any]]:
    results = []
    project_dir = project_dir or os.getcwd()
    for agent in agents:
        installed = []
        skipped = []
        error = None
        try:
            skills_dir = agent.get_skills_dir(scope, project_dir)
            os.makedirs(skills_dir, exist_ok=True)
            for skill in skills:
                dest = os.path.join(skills_dir, skill["name"])
                if os.path.exists(dest) and not force:
                    skipped.append(skill["name"])
                    continue
                
                if os.path.exists(dest):
                    if os.path.isdir(dest):
                        shutil.rmtree(dest)
                    else:
                        os.remove(dest)
                        
                shutil.copytree(skill["path"], dest)
                installed.append(skill["name"])
        except Exception as e:
            error = str(e)
            
        results.append({
            "agent": agent,
            "installed": installed,
            "skipped": skipped,
            "error": error
        })
    return results

def run_skills_flow(force: bool = False, project_dir: str = None) -> None:
    project_dir = project_dir or os.getcwd()
    print("Checking agent skills...")
    try:
        temp_dir = clone_skills_repo()
    except Exception as e:
        print(f"Warning: {e}")
        return

    try:
        skills = discover_skills(temp_dir)
        if not skills:
            print("No skills found in the repository.")
            return

        print(f"Discovered {len(skills)} skills: {', '.join(s['name'] for s in skills)}")
        # Detect present agents
        detected_agents = [agent for agent in AGENTS if agent.detect()]
        
        # Always include project-level workspace agents folder '.agents'
        workspace_agent = [a for a in AGENTS if a.id == "agents"][0]
        if workspace_agent not in detected_agents:
            detected_agents.append(workspace_agent)

        print(f"Installing skills into detected agents: {', '.join(a.name for a in detected_agents)}")
        results = install_skills(detected_agents, skills, force=force, scope="project", project_dir=project_dir)
        for res in results:
            agent_name = res["agent"].name
            if res["error"]:
                print(f"  Failed to install skills for {agent_name}: {res['error']}")
            else:
                inst_count = len(res["installed"])
                skip_count = len(res["skipped"])
                print(f"  {agent_name}: installed {inst_count}, skipped {skip_count}")

        skills_version = "1.0.0"
        pkg_json_path = os.path.join(temp_dir, "package.json")
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    if "version" in pkg:
                        skills_version = pkg["version"]
            except Exception:
                pass

        # Save to pyproject.toml if exists
        pyproject_path = os.path.join(project_dir, "pyproject.toml")
        if os.path.exists(pyproject_path):
            try:
                with open(pyproject_path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "[tool.nitrostack]" not in content:
                    content += f"\n[tool.nitrostack]\nskills_version = \"{skills_version}\"\n"
                else:
                    import re
                    if re.search(r'skills_version\s*=', content):
                        content = re.sub(r'skills_version\s*=\s*".*?"', f'skills_version = "{skills_version}"', content)
                    else:
                        # Append under existing [tool.nitrostack]
                        content = content.replace("[tool.nitrostack]", f"[tool.nitrostack]\nskills_version = \"{skills_version}\"")
                with open(pyproject_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception:
                pass
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
