"""GitHub erişimi — gh CLI üzerinden; token env ile, repo dışı."""

from __future__ import annotations

import json
import os
import subprocess


class GithubHatasi(Exception):
    pass


class Github:
    def __init__(self, repo: str, token_file: str) -> None:
        self.repo = repo
        self.token_file = token_file

    def _ortam(self) -> dict:
        try:
            token = open(self.token_file, encoding="utf-8").read().strip()
        except OSError as h:
            raise GithubHatasi(f"token okunamadı: {self.token_file}") from h
        if not token:
            raise GithubHatasi("token boş")
        return {**os.environ, "GH_TOKEN": token, "GITHUB_TOKEN": token}

    def _gh(self, *arg: str) -> str:
        try:
            s = subprocess.run(["gh", *arg], capture_output=True, text=True,
                               timeout=60, env=self._ortam())
        except (OSError, subprocess.SubprocessError) as h:
            raise GithubHatasi(f"gh çalıştırılamadı: {h}") from h
        if s.returncode != 0:
            raise GithubHatasi(f"gh {arg[0]} hatası: {s.stderr.strip()[:300]}")
        return s.stdout

    def pr(self, no: int) -> dict:
        return json.loads(self._gh("pr", "view", str(no), "--repo", self.repo,
                                   "--json", "number,headRefName,baseRefName,headRefOid,state,mergedAt"))

    def durumlar(self, sha: str) -> dict[str, str]:
        veri = json.loads(self._gh("api", f"repos/{self.repo}/commits/{sha}/status"))
        cikti: dict[str, str] = {}
        for s in veri.get("statuses") or []:
            ctx = s.get("context")
            if not ctx or ctx in cikti:
                continue
            cikti[ctx] = str(s.get("state") or "")
        return cikti

    def acik_prlar(self) -> list[dict]:
        return json.loads(self._gh("pr", "list", "--repo", self.repo, "--state", "open",
                                   "--json", "number,headRefName,headRefOid,isDraft",
                                   "--limit", "50"))
