"""Ajan işçileri — klon, DSH, karar, PR."""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import subprocess
from pathlib import Path

from . import dsh, github, govde, roles, yorum


class IsciHatasi(Exception):
    pass


def slug(metin: str, uzunluk: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", metin.strip().lower()).strip("-")
    return (s[:uzunluk].strip("-") or "gorev")


def dal_adi(instance: str, gorev: str) -> str:
    return f"agents/{slug(instance)}-{slug(gorev)}"


def _token(ajan: dict) -> str:
    try:
        t = Path(ajan["token_file"]).read_text(encoding="utf-8").strip()
    except OSError as h:
        raise IsciHatasi(f"token okunamadı: {ajan['token_file']}") from h
    if not t:
        raise IsciHatasi("token boş")
    return t


def _git_env(token: str) -> dict:
    kimlik = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {**os.environ,
            "GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "http.extraheader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {kimlik}",
            "GIT_CONFIG_KEY_1": "credential.helper",
            "GIT_CONFIG_VALUE_1": "",
            "GIT_TERMINAL_PROMPT": "0"}


def _git(workdir: Path, *arg: str, token: str) -> str:
    s = subprocess.run(["git", "-C", str(workdir), *arg], capture_output=True,
                       text=True, env=_git_env(token), timeout=120)
    if s.returncode != 0:
        raise IsciHatasi(f"git {arg[0]}: {s.stderr.strip()[:400]}")
    return s.stdout


def klon_hazirla(cfg: dict, ajan: dict) -> Path:
    wd = Path(cfg["workdir"])
    token = _token(ajan)
    if (wd / ".git").is_dir():
        _git(wd, "fetch", "origin", "--prune", token=token)
        return wd
    wd.parent.mkdir(parents=True, exist_ok=True)
    s = subprocess.run(
        ["git", "clone", f"https://github.com/{cfg['repo']}.git", str(wd)],
        capture_output=True, text=True, env=_git_env(token), timeout=300)
    if s.returncode != 0:
        raise IsciHatasi(f"klon: {s.stderr.strip()[:300]}")
    return wd


def _izin(cfg: dict, ajan: dict) -> str:
    if cfg.get("sandbox") == "yok":
        return ""
    if "permission" in ajan:
        return str(ajan["permission"])
    return str(ajan.get("permission") or ("workspace-write" if ajan["role"] == "developer" else "read-only"))


def _rol_metni(rol: str) -> str:
    return (Path(__file__).resolve().parents[1] / "roles" / f"{rol}.md").read_text(encoding="utf-8")


def gorev_al(cfg: dict, ajan: dict) -> dict | None:
    g = github.Github(cfg["repo"], ajan["token_file"])
    etiket = cfg.get("gorev_etiketi", "agents/gorev")
    for i in g.gorevler(etiket):
        if i.get("pull_request"):
            continue
        return {"no": int(i["number"]), "baslik": i.get("title") or "",
                "govde": i.get("body") or ""}
    yerel = Path(cfg["state_dir"]) / "gorevler"
    for p in sorted(yerel.glob("*.md")):
        return {"no": None, "baslik": p.stem, "govde": p.read_text(encoding="utf-8"),
                "dosya": str(p)}
    return None


# Doğrulama komutu tanımlı değilse en az sözdizimi kontrolü koşar; gövdedeki
# "çıkış 0" kanıtı bu çıktıdan gelir (uydurma kanıt yok).
VARSAYILAN_TEST = "python3 -m compileall -q ."


def _degisen_dosyalar(wd: Path, ilk: str, son: str, token: str) -> list[str]:
    try:
        cikti = _git(wd, "diff", "--name-only", f"{ilk}..{son}", token=token)
    except IsciHatasi:
        return []
    return [s.strip() for s in cikti.splitlines() if s.strip()][:100]


def _dogrulama_calistir(wd: Path, cfg: dict) -> list[str]:
    """test_command'ı temiz ortamda koşar; gövdeye makine kanıtı döndürür."""
    komut = str(cfg.get("test_command") or VARSAYILAN_TEST)
    zaman = int(cfg.get("test_timeout") or 900)
    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}
    try:
        s = subprocess.run(komut, shell=True, cwd=wd, env=env, timeout=zaman,
                           capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        return [f"- `{komut}` → çıkış 124 (zaman aşımı {zaman}s): BAŞARISIZ"]
    except OSError as h:
        return [f"- `{komut}` → çalıştırılamadı: {h}"[:400]]
    kuyruk = [x for x in (s.stdout + s.stderr).strip().splitlines() if x.strip()][-3:]
    satirlar = [f"- `{komut}` → çıkış {s.returncode}"
                + (" (BAŞARISIZ)" if s.returncode else "")]
    satirlar += [f"  - {x.strip()[:200]}" for x in kuyruk]
    return satirlar


def gorev_baslat(cfg: dict, ajan: dict, gorev: str) -> dict:
    wd = klon_hazirla(cfg, ajan)
    token = _token(ajan)
    dal = dal_adi(cfg["instance"], gorev)
    _git(wd, "checkout", "-B", dal, token=token)
    once = _git(wd, "rev-parse", "HEAD", token=token).strip()
    prompt = chr(10).join([_rol_metni(ajan["role"]), "", "## Görev", gorev, "",
                           "Yalnız dosyaları düzenle. Commit/push YOK; sürücü yapacak.",
                           "Dosyayı write aracıyla MUTLAKA oluştur; yalnız metin yanıtı verme."])
    kod, cikti = dsh.calistir(prompt, cfg.get("dsh_profile", "agents-dev"), wd, _izin(cfg, ajan), cfg.get("dsh_home"), cfg.get("dsh_patch"), wd)
    if kod != 0:
        raise IsciHatasi(f"DSH çıkış {kod}: {cikti[-500:]}")
    (Path(cfg["state_dir"]) / "dsh-son.log").write_text(cikti, encoding="utf-8")
    if _git(wd, "status", "--porcelain", token=token).strip():
        _git(wd, "add", "-A", token=token)
        _git(wd, "-c", "user.name=agents", "-c", "user.email=agents@localhost",
             "commit", "-m", f"agents: {gorev[:70]}", token=token)
    son = _git(wd, "rev-parse", "HEAD", token=token).strip()
    if son == once:
        raise IsciHatasi("DSH değişiklik üretmedi: " + cikti[-400:])
    govde_metni = govde.olustur(
        gorev,
        _degisen_dosyalar(wd, once, son, token),
        _dogrulama_calistir(wd, cfg) if not cfg.get("dogrulama_atla") else [
            "- Doğrulama atlandı (dogrulama_atla=true)."],
        neden=cfg.get("govde_neden"),
    )
    (Path(cfg["state_dir"]) / "pr-govdesi.md").write_text(govde_metni, encoding="utf-8")
    _git(wd, "push", "-u", "origin", dal, token=token)
    g = github.Github(cfg["repo"], ajan["token_file"])
    pr = g.pr_olustur(f"agents: {gorev[:60]}", govde_metni, cfg["base_branch"], dal)
    # Geliştirici ASLA merge etmez. Tek ajanlı/eksik rollü config'lerde bile
    # kapı (i5 incelemesi + i3 kararı) atlanmaz; PR karar bekler.
    return {"pr": pr.get("number"), "sha": son, "dal": dal, "workdir": str(wd)}


def karar_ayikla(metin: str, nonce: str) -> dict | None:
    desen = re.compile(r"KARAR_JSON_BEGIN\s+" + re.escape(nonce) + r"\s*\n(.*?)\nKARAR_JSON_END\s+"
                       + re.escape(nonce), re.S)
    m = desen.search(metin)
    if not m:
        return None
    try:
        veri = json.loads(m.group(1))
    except ValueError:
        return None
    return veri if isinstance(veri, dict) else None


DENETIM_ALANLARI = (
    "gömülü sır", "komut çalıştırma", "dosya/yol", "ağ/tls", "kimlik/yetki",
    "girdi doğrulama", "sır sızıntısı", "bağımlılık", "dos/maliyet",
    "kalıcılık/geri dönüş", "kapsayıcı/servis", "test kanıtı",
)
_DENETIM_ES = {
    "gomulu sir": "gömülü sır", "komut calistirma": "komut çalıştırma",
    "dosya/yol": "dosya/yol", "ag/tls": "ağ/tls", "kimlik/yetki": "kimlik/yetki",
    "girdi dogrulama": "girdi doğrulama", "sir sizintisi": "sır sızıntısı",
    "bagimlilik": "bağımlılık", "dos/maliyet": "dos/maliyet",
    "kalicilik/geri donus": "kalıcılık/geri dönüş", "kapsayici/servis": "kapsayıcı/servis",
    "test kaniti": "test kanıtı",
}


def _alan_norm(ad: object) -> str:
    s = str(ad).strip().casefold()
    return _DENETIM_ES.get(s, s)


def _karar_kapisi(karar: dict, no: int, sha: str, nonce: str) -> list[str]:
    """Eski karar_dogrula kapısının çekirdeği: fail-closed, kanıtlı ve tam kapsam."""
    hatalar: list[str] = []
    if str(karar.get("nonce") or "") != nonce:
        hatalar.append("nonce eksik/yanlış")
    if str(karar.get("sha") or "") != sha or str(karar.get("pr") or "") != str(no):
        hatalar.append("sha/pr uyuşmuyor")
    karar_turu = str(karar.get("karar") or "").strip().casefold()
    if karar_turu not in {"onay", "sorun", "red"}:
        hatalar.append(f"geçersiz karar: {karar_turu!r}")
    onem = str(karar.get("onem") or "").strip().casefold()
    if onem not in {"yuksek", "orta", "dusuk"}:
        hatalar.append(f"geçersiz önem: {onem!r}")
    denetlenen = {_alan_norm(x) for x in (karar.get("denetlenen") or [])}
    eksik = [a for a in DENETIM_ALANLARI if a not in denetlenen]
    if eksik:
        hatalar.append("denetlenen eksik: " + ", ".join(eksik))
    bulgular = karar.get("bulgular") or []
    if not isinstance(bulgular, list):
        hatalar.append("bulgular liste değil")
        bulgular = []
    yuksek = False
    for i, b in enumerate(bulgular, 1):
        if not isinstance(b, dict):
            hatalar.append(f"bulgu {i}: nesne değil")
            continue
        if str(b.get("onem") or "").strip().casefold() == "yuksek":
            yuksek = True
        if karar_turu != "onay":
            for alan in ("dosya", "satir", "aciklama", "kabul"):
                if not str(b.get(alan) or "").strip():
                    hatalar.append(f"bulgu {i}: {alan} zorunlu")
            try:
                if int(b.get("satir") or 0) <= 0:
                    hatalar.append(f"bulgu {i}: satir > 0 olmalı")
            except (TypeError, ValueError):
                hatalar.append(f"bulgu {i}: satir sayı değil")
    if karar_turu == "onay" and yuksek:
        hatalar.append("yuksek bulgu varken onay verilemez")
    if karar_turu in {"sorun", "red"} and not bulgular:
        hatalar.append(f"{karar_turu} kararında bulgu zorunlu")
    return hatalar


def incele(cfg: dict, ajan: dict, pr: dict) -> dict:
    g = github.Github(cfg["repo"], ajan["token_file"])
    no = int(pr["number"])
    sha = str(pr["head"]["sha"])
    dosyalar = g.pr_dosyalari(no)
    parcalar = []
    for d in dosyalar[:20]:
        yama = str(d.get("patch") or "")
        parcalar.append("### " + str(d.get("filename")) + chr(10) + yama[:4000])
    diff = chr(10).join(parcalar)[:30000]
    nonce = secrets.token_hex(16)
    prompt = chr(10).join([
        _rol_metni("reviewer"),
        "",
        f"## PR #{no} · {sha[:12]}",
        "Değişiklik:",
        diff,
        "",
        "SADECE aşağıdaki JSON şablonunu doldur; blok dışında HİÇBİR metin yazma.",
        "JSON geçerli olmalı; '...' yerine gerçek değer, listelerde açıklama kullan.",
        f"KARAR_JSON_BEGIN {nonce}",
        '{"makine":"reviewer","pr":' + str(no) + ',"sha":"' + sha + '","nonce":"' + nonce + '","karar":"onay",'
        '"onem":"dusuk","ozet":"kisa ozet","bulgular":[],"denetlenen":['
        '"gomulu sir","komut calistirma","dosya/yol","ag/TLS","kimlik/yetki",'
        '"girdi dogrulama","sir sizintisi","bagimlilik","DoS/maliyet",'
        '"kalicilik/geri donus","kapsayici/servis","test kaniti"],'
        '"bulgular_kaniti":"sorun/red ise her bulgu {dosya,satir,onem,aciklama,kabul} içermeli"}',
        f"KARAR_JSON_END {nonce}",
    ])
    kod, cikti = dsh.calistir(prompt, cfg.get("dsh_profile", "agents-dev"), Path(cfg["workdir"]),
                              _izin(cfg, ajan), cfg.get("dsh_home"), cfg.get("dsh_patch"),
                              Path(cfg["workdir"]))
    (Path(cfg["state_dir"]) / "dsh-reviewer.log").write_text(cikti, encoding="utf-8")
    if kod != 0 or "SERVER:" in cikti or "Model şu anda dolu" in cikti:
        raise IsciHatasi(f"DSH geçici hata (yeniden denenecek): {cikti[-200:]}")
    karar = karar_ayikla(cikti, nonce)
    if not karar or str(karar.get("sha")) != sha or str(karar.get("pr")) != str(no):
        g.durum_yaz(sha, roles.INCELEME, "failure", "karar bloğu yok/geçersiz")
        return {"durum": "failure", "neden": "karar bloğu yok/geçersiz"}
    hatalar = _karar_kapisi(karar, no, sha, nonce)
    if hatalar:
        hata_yorumu = dict(karar)
        hata_yorumu["karar"] = "sorun"
        hata_yorumu["ozet"] = "karar kapısı reddetti: " + "; ".join(hatalar)[:300]
        yorum.inceleme_yorumu(g, no, sha, hata_yorumu)
        g.durum_yaz(sha, roles.INCELEME, "failure",
                    "karar kapısı: " + "; ".join(hatalar)[:100])
        return {"durum": "failure", "neden": "karar kapısı", "hatalar": hatalar}
    onay = karar.get("karar") == "onay"
    yorum.inceleme_yorumu(g, no, sha, karar)
    g.durum_yaz(sha, roles.INCELEME, "success" if onay else "failure",
                f"{karar.get('karar')} · {karar.get('ozet', '')}")
    return {"durum": "success" if onay else "failure", "karar": karar}


def _inceleme_yorumu(g, no: int, sha: str, karar: dict) -> None:
    """İnceleme sonucunu PR'a yorum olarak yaz (durum satırı tek başına yetersiz)."""
    bulgular = karar.get("bulgular") or []
    denetlenen = karar.get("denetlenen") or []
    satirlar = [
        f"## İnceleme · `{sha[:12]}`",
        "",
        f"**Karar:** {karar.get('karar', '-')}",
        f"**Önem:** {karar.get('onem', '-')}",
        f"**Özet:** {karar.get('ozet', '-')}",
        "",
        "### Bulgular",
    ]
    if isinstance(bulgular, list) and bulgular:
        for b in bulgular:
            if isinstance(b, dict):
                yer = f"{b.get('dosya', '-')}:{b.get('satir', '-')}"
                satirlar.append(f"- `{yer}` — {b.get('aciklama', '-')} "
                                f"(kabul: {b.get('kabul', '-')})")
            else:
                satirlar.append(f"- {b}")
    else:
        satirlar.append("- Bulgu yok.")
    satirlar += ["", "### Denetlenen"]
    if isinstance(denetlenen, list) and denetlenen:
        for d in denetlenen:
            satirlar.append(f"- {d}")
    else:
        satirlar.append("- Belirtilmedi.")
    satirlar += ["", "_Otomatik inceleme (i5)._"]
    etiket = "guvenlik/onay" if karar.get("karar") == "onay" else "guvenlik/sorun"
    imza = "İnceleme · " + sha[:12]
    try:
        mevcut = g.yorumlar(no)
        if not any(imza in str(y.get("body", "")) for y in mevcut):
            g.yorum_yaz(no, chr(10).join(satirlar))
        g.etiket_ekle(no, [etiket])
    except Exception as hata:  # noqa: BLE001 - yorum yazılamasa da durum yazılmalı
        # Yetki eksikse sessiz kalma: durum açıklamasında görünür.
        try:
            g.durum_yaz(sha, roles.INCELEME, "failure",
                        f"yorum/etiket yazılamadı: {str(hata)[:80]}")
        except Exception:  # noqa: BLE001
            pass


def karar_ver(cfg: dict, ajan: dict, pr: dict) -> dict:
    g = github.Github(cfg["repo"], ajan["token_file"])
    no = int(pr["number"])
    sha = str(pr["head"]["sha"])
    d = g.durumlar(sha)
    # Kapı koşulsuzdur: config'te reviewer olmasa da inceleme onayı olmadan
    # birleştirme yok (fail-closed).
    if d.get(roles.INCELEME) != "success":
        return {"durum": "bekle", "neden": "inceleme onayı yok"}
    # Gövde kapısı: sürücünün açtığı PR'larda ayrıntılı gövde yoksa merge yok.
    # İnsan PR'ları kapsam dışı (yoksa insan PR'ı asla birleşemezdi).
    eksik = (govde.eksikler(str(pr.get("body") or ""))
             if govde.gerekli(pr, cfg.get("gorev_etiketi", "agents/gorev")) else [])
    if eksik:
        # Durum yazılmaz: gövde düzeltilince aynı sha yeniden denenebilsin.
        try:
            yorum.govde_eksik_yorumu(g, no, sha, eksik)
        except Exception:  # noqa: BLE001 - yorum yazılamasa da karar kapalı kalır
            pass
        return {"durum": "bekle", "neden": "PR gövdesi eksik", "eksikler": eksik}
    i5 = yorum.i5_karari(g, no, sha)
    if not i5 or str(i5.get("karar")) != "onay":
        g.durum_yaz(sha, roles.KARAR, "failure", "i5 karar yorumu yok/uyuşmuyor")
        yorum.karar_yorumu(g, no, sha, i5, {"durum": "failure"})
        return {"durum": "failure", "neden": "i5 karar yorumu yok/uyuşmuyor"}
    # Zorunlu durum kontrolü merge'den ÖNCE success olmalı; aksi hâlde
    # "guvenlik/karar" kontrolü merge'i kilitler.
    g.durum_yaz(sha, roles.KARAR, "success", "birleştirme onayı")
    try:
        g.birlestir(no, sha)
        g.durum_yaz(sha, roles.KARAR, "success", "birleştirildi")
        yorum.karar_yorumu(g, no, sha, i5, {"durum": "success"})
        try:
            g.etiket_ekle(no, ["karar/verildi"])
        except Exception:  # noqa: BLE001 - etiket merge sonucunu engellemez
            pass
        return {"durum": "success", "pr": no}
    except github.GithubHatasi as h:
        g.durum_yaz(sha, roles.KARAR, "failure", str(h)[:120])
        yorum.karar_yorumu(g, no, sha, i5, {"durum": "failure"})
        return {"durum": "failure", "neden": str(h)}
