"""Sync plans and running them (with zip backups of whatever gets overwritten)."""
from __future__ import annotations

import os
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import app_dir
from .diff import CHANGED, CLOUD_ONLY, LOCAL_ONLY
from .folders import local_file
from .util import prune_empty_dirs, safe_name


@dataclass
class SyncPlan:
    direction: str                     # "up" (PC -> cloud) or "down" (cloud -> PC)
    transfer: list = field(default_factory=list)
    delete: list = field(default_factory=list)
    at_risk: list = field(default_factory=list)   # changes on the target that will be lost

    @property
    def empty(self) -> bool:
        return not self.transfer and not self.delete


def make_plan(diff, direction: str, mirror_deletes: bool = True) -> SyncPlan:
    up = direction == "up"
    src_only = LOCAL_ONLY if up else CLOUD_ONLY
    dst_only = CLOUD_ONLY if up else LOCAL_ONLY
    target = "cloud" if up else "local"
    plan = SyncPlan(direction)
    for e in diff:
        if e.status in (src_only, CHANGED):
            plan.transfer.append(e)
        elif e.status == dst_only and mirror_deletes:
            plan.delete.append(e)
        else:
            continue
        if e.changed_side in (target, "both") or (e.status == CHANGED and e.changed_side is None):
            plan.at_risk.append(e)
    return plan


def backup_files(files: dict, game: str, keep: int = 20):
    """Zip local files ({cloud path: file on this PC}) that are about to be replaced or deleted."""
    files = {r: p for r, p in files.items() if Path(p).is_file()}
    if not files:
        return None
    d = app_dir() / "backups" / safe_name(game)
    d.mkdir(parents=True, exist_ok=True)
    zp = d / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}_before-sync-down.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for r, p in files.items():
            z.write(p, r)
    for old in sorted(d.glob("*.zip"))[:-keep]:
        old.unlink(missing_ok=True)
    return zp


def backup_cloud(backend, game: str, rels, keep: int = 20):
    """Zip the cloud versions of files that are about to be overwritten (used for conflicts)."""
    if not rels:
        return None
    d = app_dir() / "backups" / safe_name(game)
    d.mkdir(parents=True, exist_ok=True)
    zp = d / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}_cloud-before-sync-up.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for r in rels:
            z.writestr(r, backend.read_bytes(game, r))
    for old in sorted(d.glob("*.zip"))[:-keep]:
        old.unlink(missing_ok=True)
    return zp


def execute_plan(plan: SyncPlan, backend, game: str, roots: dict, log=print):
    """roots: {folder id: path on this PC} (see core/folders.py)."""
    total = len(plan.transfer) + len(plan.delete)
    i = 0
    backup = None
    if plan.direction == "up":
        risky = [e.path for e in plan.at_risk if e.cloud]
        if risky:
            backup = backup_cloud(backend, game, risky)
            log(f"Backed up {len(risky)} cloud file(s) to {backup}")
        for e in plan.transfer:
            i += 1
            log(f"[{i}/{total}] Upload  {e.path}")
            backend.upload(game, e.path, local_file(roots, e.path)[1], e.local.mtime)
        for e in plan.delete:
            i += 1
            log(f"[{i}/{total}] Delete from cloud  {e.path}")
            backend.delete(game, e.path)
    else:
        for root in roots.values():
            if root:
                Path(root).mkdir(parents=True, exist_ok=True)
        affected = [e.path for e in plan.transfer if e.local] + [e.path for e in plan.delete]
        backup = backup_files({r: local_file(roots, r)[1] for r in affected}, game)
        if backup:
            log(f"Backed up {len(affected)} local file(s) to {backup}")
        for e in plan.transfer:
            i += 1
            log(f"[{i}/{total}] Download  {e.path}")
            dest = local_file(roots, e.path)[1]
            dest.parent.mkdir(parents=True, exist_ok=True)
            backend.download(game, e.path, dest)
            if e.cloud and e.cloud.mtime:
                try:
                    os.utime(dest, (time.time(), e.cloud.mtime))
                except OSError:
                    pass
        for e in plan.delete:
            i += 1
            log(f"[{i}/{total}] Delete on this PC  {e.path}")
            root, p = local_file(roots, e.path)
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            prune_empty_dirs(p.parent, root)
    return backup
