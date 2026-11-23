"""Named access to local studio operations shared with the browser."""
from __future__ import annotations

from pathlib import Path
from string import Formatter
from urllib.parse import quote

JOB = "/api/jobs/{char}/{jid}"
OPERATIONS = {
    "jobs": ("GET", "/api/jobs"),
    "job": ("GET", JOB),
    "create-job": ("POST", "/api/jobs"),
    "update-job": ("POST", JOB + "/settings"),
    "archive-job": ("POST", JOB + "/archive"),
    "run-stage": ("POST", JOB + "/run"),
    "restore-take": ("POST", JOB + "/restore"),
    "read-prompts": ("GET", JOB + "/prompts"),
    "save-prompt-notes": ("POST", JOB + "/prompts"),
    "profiles": ("GET", "/api/profiles"),
    "save-profile": ("POST", "/api/profiles"),
    "create-variant": ("POST", JOB + "/variant"),
    "stack-gifs": ("POST", JOB + "/stack_gif"),
    "configure-effect": ("POST", JOB + "/effect"),
    "attach-effect": ("POST", JOB + "/attach"),
    "export-item": ("POST", JOB + "/export_item"),
    "project-camera": ("GET", "/api/project/camera"),
    "set-project-camera": ("POST", "/api/project/camera"),
    "job-camera": ("GET", JOB + "/camera"),
    "set-job-camera": ("POST", JOB + "/camera"),
    "set-mirror-policy": ("POST", JOB + "/mirror_policy"),
    "motions": ("GET", "/api/motions"),
    "add-motion": ("POST", "/api/motions"),
    "approve-motion": ("POST", "/api/motions/{name}/approve"),
    "queue": ("GET", "/api/queue"),
    "cancel-task": ("POST", "/api/queue/{tid}/cancel"),
    "retry-task": ("POST", "/api/queue/{tid}/retry"),
    "clear-finished": ("POST", "/api/queue/clear"),
}


async def invoke(base: Path | str, operation: str, *, parameters: dict | None = None,
                 body: dict | None = None, query: dict | None = None):
    if operation not in OPERATIONS:
        raise ValueError(f"Unknown studio operation {operation!r}.")
    method, template = OPERATIONS[operation]
    parameters = parameters or {}
    required = {field for _, field, _, _ in Formatter().parse(template) if field}
    if parameters.keys() != required:
        raise ValueError(f"{operation} expects path parameters: {', '.join(sorted(required)) or 'none'}.")
    for value in parameters.values():
        if not isinstance(value, str) or value.strip() in ("", ".", "..") or "/" in value or "\\" in value:
            raise ValueError("Studio path parameters must be plain names or IDs.")
    if body is not None and (method != "POST" or not isinstance(body, dict)):
        raise ValueError("Only write operations accept a JSON object body.")
    path = template.format_map({key: quote(value, safe="") for key, value in parameters.items()})
    import httpx

    from .ui.server import create_app

    transport = httpx.ASGITransport(app=create_app(base, worker=False), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://spritewaffle.local", trust_env=False) as client:
        options = {"json": body or {}} if method == "POST" else {}
        response = await client.request(method, path, params=query, **options)
    if response.is_error:
        if response.status_code >= 500:
            raise RuntimeError(f"The local {operation} operation failed. Run it with the browser or inspect the job.")
        raise ValueError(response.json().get("detail", response.reason_phrase))
    return response.json()
