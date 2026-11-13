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

    def _istek(self, yontem: str, yol: str, veri: dict | None = None):
        govde = None if veri is None else json.dumps(veri).encode("utf-8")
        istek = urllib.request.Request(
            API + yol, data=govde, method=yontem,
            headers={"Authorization": f"Bearer {self._token()}",
                     "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json",
                     "User-Agent": "agents"},
        )
        try:
            with urllib.request.urlopen(istek, timeout=30) as y:
                ham = y.read().decode("utf-8")
                return json.loads(ham) if ham else {}
        except (urllib.error.URLError, ValueError) as h:
            raise GithubHatasi(f"GitHub {yontem} {yol}: {h}") from h

    def pr(self, no: int) -> dict:
        return self._istek("GET", f"/repos/{self.repo}/pulls/{no}")

    def durumlar(self, sha: str) -> dict[str, str]:
        veri = self._istek("GET", f"/repos/{self.repo}/commits/{sha}/status")
        cikti: dict[str, str] = {}
        for s in veri.get("statuses") or []:
            ctx = s.get("context")
            if not ctx or ctx in cikti:
                continue
            cikti[ctx] = str(s.get("state") or "")
        return cikti

    def acik_prlar(self) -> list[dict]:
        return self._istek("GET", f"/repos/{self.repo}/pulls?state=open&per_page=50")

    def durum_yaz(self, sha: str, baglam: str, durum: str, aciklama: str) -> dict:
        return self._istek("POST", f"/repos/{self.repo}/statuses/{sha}", {
            "state": durum, "context": baglam, "description": aciklama[:140],
        })

    def pr_olustur(self, baslik: str, govde: str, bas: str, head: str) -> dict:
        return self._istek("POST", f"/repos/{self.repo}/pulls", {
            "title": baslik, "body": govde, "base": bas, "head": head,
        })

    def birlestir(self, no: int, sha: str) -> dict:
        return self._istek("PUT", f"/repos/{self.repo}/pulls/{no}/merge", {
            "merge_method": "squash", "sha": sha,
        })
