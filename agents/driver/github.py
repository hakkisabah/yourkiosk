"""GitHub REST — stdlib; gh CLI gerekmez."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

API = "https://api.github.com"


class GithubHatasi(Exception):
    pass


class Github:
    def __init__(self, repo: str, token_file: str) -> None:
        self.repo = repo
        self.token_file = token_file

    def _token(self) -> str:
        try:
            token = open(self.token_file, encoding="utf-8").read().strip()
        except OSError as h:
            raise GithubHatasi(f"token okunamadı: {self.token_file}") from h
        if not token:
            raise GithubHatasi("token boş")
        return token

    def _get(self, yol: str):
        istek = urllib.request.Request(
            API + yol,
            headers={"Authorization": f"Bearer {self._token()}",
                     "Accept": "application/vnd.github+json",
                     "User-Agent": "agents"},
        )
        try:
            with urllib.request.urlopen(istek, timeout=30) as y:
                return json.loads(y.read().decode("utf-8"))
        except (urllib.error.URLError, ValueError) as h:
            raise GithubHatasi(f"GitHub: {h}") from h

    def pr(self, no: int) -> dict:
        return self._get(f"/repos/{self.repo}/pulls/{no}")

    def durumlar(self, sha: str) -> dict[str, str]:
        veri = self._get(f"/repos/{self.repo}/commits/{sha}/status")
        cikti: dict[str, str] = {}
        for s in veri.get("statuses") or []:
            ctx = s.get("context")
            if not ctx or ctx in cikti:
                continue
            cikti[ctx] = str(s.get("state") or "")
        return cikti

    def acik_prlar(self) -> list[dict]:
        return self._get(f"/repos/{self.repo}/pulls?state=open&per_page=50")
