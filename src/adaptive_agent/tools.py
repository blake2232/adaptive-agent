"""Tools exposed to agent code. File access is confined to a workdir; shell and web are opt-in."""
import os, subprocess, urllib.request
from pathlib import Path


class ToolError(Exception):
    pass


class Tools:
    def __init__(self, workdir=".", allow_shell=False, allow_web=False, shell_timeout=10, max_bytes=200_000):
        self.workdir = Path(workdir).resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.allow_shell, self.allow_web = allow_shell, allow_web
        self.shell_timeout, self.max_bytes = shell_timeout, max_bytes

    def _path(self, rel):
        p = (self.workdir / rel).resolve()
        if p != self.workdir and self.workdir not in p.parents:
            raise ToolError(f"path escapes workdir: {rel}")
        return p

    def read_file(self, path):
        return self._path(path).read_text()[: self.max_bytes]

    def write_file(self, path, content):
        p = self._path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return str(p.relative_to(self.workdir))

    def shell(self, cmd):
        """Run a command in the workdir with a timeout and scrubbed env. NOT a security sandbox."""
        if not self.allow_shell:
            raise ToolError("shell tool disabled (use --allow-shell)")
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.workdir)}
        r = subprocess.run(cmd, shell=True, cwd=self.workdir, env=env, capture_output=True,
                           text=True, timeout=self.shell_timeout)
        return {"returncode": r.returncode, "stdout": r.stdout[-self.max_bytes:], "stderr": r.stderr[-5000:]}

    def web_fetch(self, url):
        if not self.allow_web:
            raise ToolError("web tool disabled (use --allow-web)")
        if not url.startswith(("http://", "https://")):
            raise ToolError("only http(s) URLs allowed")
        req = urllib.request.Request(url, headers={"User-Agent": "adaptive-agent/0.1"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read(self.max_bytes).decode("utf-8", "replace")
