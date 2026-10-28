"""GÜNCELLEME KAPISI — imzalayanın KİMLİĞİ ve `--kuru`nun dokunmazlığı (27 Ekim i5 bulguları).

BULGU 5 (ORTA): `git verify-tag` yalnız "imza GEÇERLİ mi" der; imzalayanın parmak izine bakmaz.
Anahtar halkası kiosk kullanıcısının yazabildiği `$KIOSK_HOME` altında olduğu için ele geçirilmiş
bir kiosk hesabı KENDİ anahtarını import edip KENDİ etiketini imzalayabiliyordu → güncelleme
kapısı "geçerli imza" diyerek açılıyordu. Beklenen: `git verify-tag --raw` çıktısındaki VALIDSIG
parmak izi ROOT'a ait beyaz liste (`/etc/yourkiosk/yayin-imzaci`) ile karşılaştırılır; uyuşmazsa
güncelleme REDDEDİLİR (fail-closed).

BULGU 6 (DÜŞÜK): `--kuru` "hiçbir şeyi değiştirmez" diyordu ama `git fetch --tags --prune --force`
kuru koşuda da çalışıp yerel etiketleri güncelliyordu. Beklenen: kuru koşuda fetch YAPILMAZ.

Testler betiği GERÇEKTEN çalıştırır: geçici bir git deposu, gerçek GPG anahtarıyla imzalanmış
`yayin-*` etiketi ve `runuser` yerine ayrıcalıksız bir vekil (test kullanıcısı = KIOSK_KULLANICI).
Bu yüzden ağ, systemctl ve gerçek cihaz GEREKMEZ: `--kuru` yolu hiçbir şeyi değiştirmez.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

DEPO = Path(__file__).resolve().parents[2]
BETIK = DEPO / "deploy" / "guncelle.sh"

GIT = shutil.which("git")
GPG = shutil.which("gpg")

pytestmark = pytest.mark.skipif(
    GIT is None or GPG is None,
    reason="git/gpg yok — güncelleme kapısı testi çalıştırılamaz",
)

SAHTE_PARMAK_IZI = "0" * 40


def _calistir(komut: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(komut, cwd=cwd, env=env, check=True, capture_output=True, text=True)


def _git(*args: str, cwd: Path, env: dict[str, str]) -> str:
    return _calistir([str(GIT), *args], cwd=cwd, env=env).stdout.strip()


def _ortam(tmp_path: Path, *, imzaci: str | None, etiket_adi: str = "yayin-20260101") -> dict:
    """Geçici depo + GPG anahtarı + imzalı etiket + betiğin ortam değişkenleri."""
    gpg_ev = tmp_path / "gnupg"
    gpg_ev.mkdir(mode=0o700)
    depo = tmp_path / "depo"
    depo.mkdir()
    kiosk_home = tmp_path / "kiosk-home"
    log_dizin = tmp_path / "loglar"
    log_dizin.mkdir()
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "runuser").write_text(
        "#!/bin/sh\n"
        "[ \"$1\" = '-u' ] || { echo \"runuser: beklenmeyen argüman\" >&2; exit 2; }\n"
        "shift 2\n"
        "[ \"${1:-}\" = '--' ] && shift\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    (shim / "runuser").chmod(0o755)

    env = {
        **os.environ,
        "GNUPGHOME": str(gpg_ev),
        "HOME": str(tmp_path),
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig"),
        "GIT_CONFIG_SYSTEM": os.devnull,
    }
    _git("init", "-q", "-b", "main", cwd=depo, env=env)
    _git("config", "user.email", "test@ornek", cwd=depo, env=env)
    _git("config", "user.name", "Test", cwd=depo, env=env)
    (depo / "dosya.txt").write_text("1\n", encoding="utf-8")
    _git("add", "dosya.txt", cwd=depo, env=env)
    _git("commit", "-q", "-m", "ilk", cwd=depo, env=env)

    _calistir(
        [str(GPG), "--batch", "--passphrase", "", "--quick-generate-key",
         "Test Imzaci <test@ornek>", "rsa2048", "sign", "1d"],
        cwd=tmp_path, env=env,
    )
    parmak_izi = ""
    for satir in _calistir(
        [str(GPG), "--with-colons", "--fingerprint"], cwd=tmp_path, env=env
    ).stdout.splitlines():
        if satir.startswith("fpr:"):
            parmak_izi = satir.split(":")[9]
            break
    assert parmak_izi, "GPG parmak izi okunamadı"

    _git("config", "user.signingkey", parmak_izi, cwd=depo, env=env)
    _git("-c", "gpg.program=" + str(GPG), "tag", "-s", etiket_adi, "-m", "yayın", cwd=depo, env=env)

    # 'origin/main' yok: kuru koşuda fetch yapılmadığını bu yüzden ayırt edebiliyoruz.
    liste = tmp_path / "yayin-imzaci"
    if imzaci is not None:
        liste.write_text(imzaci + "\n", encoding="utf-8")

    return {
        "depo": depo,
        "parmak_izi": parmak_izi,
        "env": {
            **env,
            "KIOSK_KOK": str(depo),
            "KIOSK_KULLANICI": os.environ.get("USER") or _kullanici(),
            "KIOSK_HOME": str(kiosk_home),
            "KIOSK_LOG_DIZIN": str(log_dizin),
            "KIOSK_YAYIN_IMZACI_DOSYASI": str(liste),
            "PATH": f"{shim}{os.pathsep}{os.environ.get('PATH', '')}",
        },
    }


def _kullanici() -> str:
    import getpass

    return getpass.getuser()


def _kuru(ortam: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(BETIK), "--kuru"],
        cwd=ortam["depo"],
        env=ortam["env"],
        capture_output=True,
        text=True,
        timeout=120,
    )


# --------------------------------------------------------------- BULGU 5
def test_eslesen_parmak_izi_kapiyi_gecirir(tmp_path: Path) -> None:
    ortam = _ortam(tmp_path, imzaci=None)
    Path(ortam["env"]["KIOSK_YAYIN_IMZACI_DOSYASI"]).write_text(
        f"# yayın imza anahtarı\n{ortam['parmak_izi'].lower()}\n", encoding="utf-8"
    )

    sonuc = _kuru(ortam)

    assert sonuc.returncode == 0, sonuc.stderr
    assert "imzalayan beyaz listede" in sonuc.stdout, sonuc.stdout
    assert "KURU: git checkout --detach yayin-20260101" in sonuc.stdout, sonuc.stdout


def test_eslesmeyen_parmak_izi_guncellemeyi_reddeder(tmp_path: Path) -> None:
    """Saldırganın kendi anahtarıyla imzaladığı etiket: imza GEÇERLİ ama imzalayan YANLIŞ."""
    ortam = _ortam(tmp_path, imzaci=SAHTE_PARMAK_IZI)

    sonuc = _kuru(ortam)

    assert "beyaz listede DEĞİL" in sonuc.stdout, sonuc.stdout
    assert "imzalayan beyaz listede" not in sonuc.stdout
    assert "KURU: git checkout --detach" not in sonuc.stdout, (
        "imzalayan kimliği uyuşmadığı hâlde güncelleme adımı planlandı"
    )
    assert "REDDEDİLDİ" in sonuc.stdout


def test_beyaz_liste_yoksa_fail_closed(tmp_path: Path) -> None:
    ortam = _ortam(tmp_path, imzaci=None)

    sonuc = _kuru(ortam)

    assert "beyaz listesi yok" in sonuc.stdout, sonuc.stdout
    assert "KURU: git checkout --detach" not in sonuc.stdout


def test_parmak_izi_bicim_denetimi_ve_validsig_ayristirma(tmp_path: Path) -> None:
    """Kapı fonksiyonları betikten ALINIP doğrudan koşulur (metin taklidi değil)."""
    ortam = _ortam(tmp_path, imzaci="abcdef")
    betik = BETIK.read_text(encoding="utf-8")
    bas = betik.index("validsig_parmak_izi()")
    bit = betik.index("etiket_dogrula()")
    fonksiyonlar = betik[bas:bit]
    liste = str(ortam["env"]["KIOSK_YAYIN_IMZACI_DOSYASI"])
    yukle = f"IMZACI_DOSYASI={liste!r}\n{fonksiyonlar}\n"
    fpr = ortam["parmak_izi"].upper()

    r = subprocess.run(
        ["bash", "-c", yukle
         + f"printf '[GNUPG:] VALIDSIG {fpr} 2026-01-01 1767225600 0 4 0 22 8 00 {fpr}\\n' | validsig_parmak_izi"],
        capture_output=True, text=True,
    )
    assert r.stdout.strip() == fpr, r.stderr

    r = subprocess.run(["bash", "-c", yukle + f"imzaci_izinli {fpr}; echo kod=$?"],
                       capture_output=True, text=True)
    assert "kod=1" in r.stdout, "biçimsiz (6 karakter) liste girdisi kabul edilmemeli"

    Path(liste).write_text(fpr + "\n", encoding="utf-8")
    r = subprocess.run(["bash", "-c", yukle + f"imzaci_izinli {fpr}; echo kod=$?"],
                       capture_output=True, text=True)
    assert "kod=0" in r.stdout

    r = subprocess.run(["bash", "-c", yukle + f"imzaci_izinli {SAHTE_PARMAK_IZI}; echo kod=$?"],
                       capture_output=True, text=True)
    assert "kod=1" in r.stdout


# --------------------------------------------------------------- BULGU 6
def test_kuru_kosu_fetch_yapmaz_ve_etiketleri_degistirmez(tmp_path: Path) -> None:
    """Depoda `origin` YOK: fetch çalışsaydı betik çıkış 6 ile dururdu (eski davranış)."""
    ortam = _ortam(tmp_path, imzaci=None)
    Path(ortam["env"]["KIOSK_YAYIN_IMZACI_DOSYASI"]).write_text(ortam["parmak_izi"] + "\n", encoding="utf-8")
    onceki = _git("tag", "--list", cwd=ortam["depo"], env=ortam["env"])

    sonuc = _kuru(ortam)

    assert sonuc.returncode == 0, sonuc.stderr
    assert "git fetch ATLANDI" in sonuc.stdout, sonuc.stdout
    assert "git fetch başarısız" not in sonuc.stdout
    assert _git("tag", "--list", cwd=ortam["depo"], env=ortam["env"]) == onceki
    assert not (ortam["depo"] / ".git" / "FETCH_HEAD").exists(), "kuru koşuda fetch izi bırakıldı"
