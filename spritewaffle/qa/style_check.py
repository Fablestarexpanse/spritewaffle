"""Compare current project rules with an asset's settings and processing records."""
from __future__ import annotations

import json
from pathlib import Path

from ..core import fsutil, job_palette, project
from ..core.job import Job
from ..core.profile import resolve
from ..prompts import styles


def _clip_findings(path: Path, wanted_style: str | None, allowed: set[str]) -> tuple[bool, list[dict]]:
    location = {"facing": path.parent.parent.name, "action": path.parent.name}
    try:
        report = json.loads(fsutil.read_text(path))
        if not isinstance(report, dict):
            raise ValueError("expected a processing report object")
    except FileNotFoundError:
        return False, [location | {"code": "clip_report_missing", "classification": "review",
                                   "message": "The clip has a frames folder and no processing record. Reprocess it to check its settings."}]
    except (ValueError, OSError):
        return False, [location | {"code": "clip_report_unreadable", "classification": "review",
                                   "message": "The processing record is unreadable. Reprocess the clip to check its settings."}]

    actual_style = report.get("style") or "pixel"
    if not isinstance(actual_style, str) or actual_style not in styles.STYLES:
        return False, [location | {"code": "clip_style_unknown", "classification": "review",
                                   "message": "This processing record has an unknown art style."}]
    findings = []
    if wanted_style and actual_style != wanted_style:
        findings.append(location | {"code": "clip_style", "classification": "warn",
                                    "message": f"The clip was processed in {styles.STYLES[actual_style]['label']}."})
    if allowed and actual_style == "pixel":
        try:
            used = set(job_palette.clean_colours(report.get("palette")))
        except ValueError:
            findings.append(location | {"code": "clip_palette_unavailable", "classification": "review",
                                        "message": "This clip has no usable palette record. Reprocess it to check its palette."})
        else:
            if outside := sorted(used - allowed):
                findings.append(location | {"code": "clip_palette", "classification": "warn", "colours": outside,
                                            "message": "The recorded processing palette contains colours outside the project palette."})
    return True, findings


def inspect(job: Job) -> dict:
    """Read a fresh report without fitting a palette, changing files, or blocking export."""
    meta = job.read_meta()
    inputs = meta["inputs"]
    record = project.read(job.root.parent.parent)
    guide = record.get("style", {})
    if not isinstance(guide, dict):
        raise ValueError("Project style must be a JSON object")
    wanted_style, wanted_profile = guide.get("default_style"), guide.get("default_profile")
    wanted_palette = job_palette.clean_colours(record["palette"]) if record.get("palette") else []
    allowed = set(wanted_palette)
    actual_style = inputs.get("style") or "pixel"
    actual_profile = inputs.get("profile") or "default"
    findings = []
    checked = 0
    fixed = None

    if not (wanted_style or wanted_profile or allowed):
        findings.append({"code": "project_style_unconfigured", "classification": "review",
                         "message": "Set a project art style, game profile, or palette to start checking consistency."})
    else:
        if wanted_style and actual_style != wanted_style:
            findings.append({"code": "asset_style", "classification": "warn",
                             "message": "The asset's art style differs from the project default."})
        try:
            profile = resolve(inputs.get("profile"))
        except (ValueError, TypeError, OSError):
            findings.append({"code": "asset_profile_unavailable", "classification": "review",
                             "message": "The asset's game profile could not be read. Check that it is installed."})
        else:
            actual_profile = profile.name
            if wanted_profile and actual_profile != wanted_profile:
                findings.append({"code": "asset_profile", "classification": "warn",
                                 "message": "The asset's game profile differs from the project default."})
            if allowed and actual_style == "pixel":
                try:
                    fixed = job_palette.current(job, profile)
                    selected = set(job_palette.clean_colours(fixed["colours"])) if fixed else set()
                except (ValueError, TypeError, OSError, KeyError):
                    fixed = None
                    selected = set()
                    findings.append({"code": "asset_palette_unavailable", "classification": "review",
                                     "message": "The asset's selected palette could not be read. Check the game profile and job palette."})
                if outside := sorted(selected - allowed):
                    findings.append({"code": "asset_palette", "classification": "warn", "colours": outside,
                                     "message": "The asset's selected palette contains colours outside the project palette."})
        if wanted_style or allowed:
            processed = job.root / "04_pixel"
            reports = set(processed.glob("*/*/pixel_report.json"))
            reports.update(p.parent.parent / "pixel_report.json" for p in processed.glob("*/*/*f/frames") if p.is_dir())
            for path in sorted(reports):
                readable, issues = _clip_findings(path, wanted_style, allowed)
                checked += readable
                findings.extend(issues)

    levels = {finding["classification"] for finding in findings}
    classification = "review" if "review" in levels else "warn" if "warn" in levels else "pass"
    return {"project_id": record["id"], "asset_id": f"{meta['character']}/{meta['job_id']}",
            "classification": classification, "clips_checked": checked,
            "rules": {"style": wanted_style, "profile": wanted_profile, "palette": wanted_palette},
            "asset": {"style": actual_style, "profile": actual_profile, "palette": fixed}, "findings": findings}
