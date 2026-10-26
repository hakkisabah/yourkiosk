"""Güncelleme hattının YETKİ MODELİ kilitli kalsın (i5 bulgusu: root, kiosk'a ait betiği çalıştırıyordu).

NEDEN: `deploy/systemd/yourkiosk-guncelle.service` root olarak çalışırken `ExecStart` depodaki
(=`kiosk` kullanıcısının yazabildiği) betiği gösterirse, ayrıcalıksız bir yerel kullanıcı o betiği
değiştirip root komutu çalıştırabilir. Aynı şekilde root, sahibi kiosk olan depoda doğrudan `git`
çağırırsa "detected dubious ownership" ile güncelleme (ve geri dönüş) kırılır.

Bu test metni denetler; davranışı değil, KURALI kilitler:
  1. Birim, root'a ait kopyayı (`/usr/local/lib/yourkiosk/`) çalıştırmalı, depodaki yolu DEĞİL.
  2. `guncelle.sh` içindeki tüm `git` çağrıları `kiok` (runuser -u kiosk) sarmalayıcısıyla olmalı.
  3. Sabit `/tmp/...` günlük yolu olmamalı (sembolik bağ saldırısı), mktemp kullanılmalı.
"""

from pathlib import Path

DEPO = Path(__file__).resolve().parents[2]
BIRIM = DEPO / "deploy" / "systemd" / "yourkiosk-guncelle.service"
BETIK = DEPO / "deploy" / "guncelle.sh"


def _birim() -> str:
    return BIRIM.read_text(encoding="utf-8")


def _betik() -> str:
    return BETIK.read_text(encoding="utf-8")


def test_birim_root_a_ait_kopyayi_calistirir():
    metin = _birim()
    exec_satirlari = [s.strip() for s in metin.splitlines() if s.strip().startswith("ExecStart=")]
    assert exec_satirlari, "ExecStart bulunamadı"
    for satir in exec_satirlari:
        yol = satir.split("=", 1)[1].strip()
        assert yol.startswith("/usr/local/lib/yourkiosk/"), (
            f"birim depodaki (kiosk'un yazabildiği) betiği çalıştırıyor: {yol}"
        )
        assert "/opt/yourkiosk" not in yol


def test_birim_kurulum_komutunu_belgeler():
    """Operatör root'a ait kopyayı nasıl kuracağını birimden/README'den görebilmeli."""
    metin = _birim()
    assert "install -Dm0755" in metin
    assert "runuser -u kiosk" in metin


def test_guncelle_betikteki_tum_git_cagrilari_kiok_ile():
    import re

    metin = _betik()
    cagri = re.compile(r"(?<![\w./-])git\s+(pull|status|rev-parse|reset|checkout|fetch|log|rev-list)\b")
    kacak = []
    for ham in metin.splitlines():
        satir = ham.strip()
        if satir.startswith("#") or satir.startswith("log "):
            continue
        # `.git` yolu, `stat -c ... .git` gibi satırlar komut çağrısı değil.
        if not cagri.search(satir):
            continue
        if "kiok git" in satir:
            continue
        kacak.append(satir)
    assert not kacak, "kiosk kullanıcısı olmadan çağrılan git komutları: " + repr(kacak)


def test_sabit_tmp_yolu_yok():
    metin = _betik()
    assert "mktemp -d" in metin
    for ham in metin.splitlines():
        satir = ham.strip()
        if satir.startswith("#"):
            continue
        assert "/tmp/yourkiosk-" not in satir, f"sabit /tmp yolu: {satir}"


def test_saglik_kapisi_mqtt_kapaliyken_atlandi_sayar():
    """Belgede/araçta 'atlandı' davranışı korunmalı (i5: her gece geri dönüş hatası)."""
    metin = _betik()
    assert "canli_test.py --sure 15" in metin
    arac = (DEPO / "kiosk" / "tools" / "canli_test.py").read_text(encoding="utf-8")
    assert "atland" in arac.lower(), "canli_test MQTT kapalıyken 'atlandı' demiyor"


# --- i5 bulguları (25.10 15:14) -------------------------------------------------

def test_saglik_denetimi_sessizce_atlanmaz():
    """Bulgu 1: .venv/canli_test yoksa güncelleme BAŞARISIZ sayılmalı.

    Önceki hâlde `elif [[ -x .venv/bin/python ... ]]` zincirinde ne servis ne araç kontrolü
    yapılıyordu: SAGLIK=0 kalıp bozuk derleme "✓ güncelleme tamam" olarak kabul ediliyordu.
    """
    metin = _betik()
    blok = metin.split("elif [[ -x kiosk/.venv/bin/python", 1)
    assert len(blok) == 2, "sağlık kapısı elif'i bulunamadı"
    kuyruk = blok[1].split("if [[ $SAGLIK -ne 0 ]]")[0]
    assert "else" in kuyruk, "sağlık kapısının else dalı yok (sessiz atlama)"
    else_dali = kuyruk.split("else", 1)[1]
    assert "SAGLIK=1" in else_dali, "else dalı güncellemeyi başarısız saymıyor"


def test_guncelleme_home_dizini_protecthome_ile_celiskiyor_mu():
    """Bulgu 2: birim ProtectHome=yes iken HOME=/home/<kullanıcı> VERİLMEMELİ.

    systemd.exec(5): ProtectHome=yes ile /home erişilemez ve boş görünür → npm/pip önbellek
    yazamaz, güncelleme her koşuda düşer.
    """
    import re

    birim = _birim()
    assert "ProtectHome=yes" in birim
    betik = _betik()
    ev_veren = [
        s.strip()
        for s in betik.splitlines()
        if re.search(r"HOME=[\"']?/home/", s) and not s.strip().startswith("#")
    ]
    assert not ev_veren, f"ProtectHome=yes ile çelişen HOME: {ev_veren}"
    # birimin HOME'u da /home altında olmamalı
    for satir in birim.splitlines():
        if satir.strip().startswith("Environment=HOME="):
            assert "/home/" not in satir, f"birim HOME=/home veriyor: {satir}"


def test_kiosk_home_kalici_ve_yazilabilir_dizin():
    """Güncelleme, kiosk kullanıcısının yazabildiği kalıcı bir HOME kullanmalı."""
    metin = _betik()
    assert 'KIOSK_HOME="${KIOSK_HOME:-/var/lib/yourkiosk-guncelle}"' in metin
    assert 'env HOME="$KIOSK_HOME"' in metin
    assert "chown \"$KIOSK_KULLANICI:$KIOSK_KULLANICI\" \"$KIOSK_HOME\"" in metin


def test_guncelleme_betigi_kopyasini_kendisi_yenilemez():
    """Bulgu 3 (25.10 19:18): root, kiosk'un YAZABİLDİĞİ betiği /usr/local/lib'e kopyalamamalı.

    Kopyayı güncelleme koşusunda depodan yenilemek yerel yetki yükseltmesidir; ayrıca birim
    ProtectSystem=full ile /usr'u salt-okunur bağladığı için böyle bir kopyalama EROFS'a düşer
    (yani 'koruma' üretimde hiç çalışmaz). Kopya AYRI bir root adımıyla kurulur.
    """
    metin = _betik()
    kacak = [
        s.strip()
        for s in metin.splitlines()
        if not s.strip().startswith("#")
        and "install" in s
        and "/usr/local/lib/yourkiosk" in s
    ]
    assert not kacak, f"güncelleme betiği kendi kopyasını root olarak kuruyor: {kacak}"
    # Kopya farklıysa operatöre NE yapacağını söylemeli (sessiz kalmamalı).
    assert "kur-guncelle-betigi.sh" in metin, "fark uyarısı operatörü doğru adıma yönlendirmiyor"


def test_ayri_kurulum_betigi_var_ve_root_ister():
    """Kopyayı kuran adım depoda ve root olmadan çalışmamalı; kirli ağaçta kurmamalı."""
    yol = DEPO / "deploy" / "kur-guncelle-betigi.sh"
    assert yol.exists(), "deploy/kur-guncelle-betigi.sh yok (kopya nasıl kurulacak?)"
    metin = yol.read_text(encoding="utf-8")
    assert "EUID -eq 0" in metin, "kurulum betiği root denetlemiyor"
    assert "bash -n" in metin, "kurulum betiği sözdizimi denetlemiyor"
    # i5 bulgusu 26.10: `git diff --quiet` yalnız çalışma ağacı ↔ INDEX farkına bakar; `git add`
    # ile stage edilen değişiklik "temiz" görünüp root:root kuruluyordu. Doğru ölçüt
    # `status --porcelain` (staged + unstaged + untracked).
    assert "status --porcelain" in metin, "kirli-ağaç kapısı staged değişikliği görmüyor"
    kullanilan = [s for s in metin.splitlines()
                  if not s.strip().startswith("#") and "diff --quiet" in s]
    assert not kullanilan, f"eski (index'i atlayan) kapı hâlâ çalıştırılıyor: {kullanilan}"
    assert "install -Dm0755 -o root -g root" in metin
    assert "cmp -s" in metin, "kurulum sonrası doğrulama yok"


def test_kirli_agac_kapisi_stage_edilmis_degisikligi_yakalar(tmp_path):
    """KAPININ ÖLÇÜTÜNÜ davranışla kanıtla: staged değişiklik `diff --quiet`ten KAÇAR.

    Bu test betiğin metnini değil, seçilen git komutunun GERÇEK davranışını sınar: `git add`
    sonrası `git diff --quiet` "temiz" der (0), `status --porcelain` ise değişikliği gösterir.
    Yani kapı `--porcelain` kullandığı sürece yerel yetki yükseltmesi mümkün değil.
    """
    import subprocess

    def git(*a: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(tmp_path), *a], capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path),
                                   "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})

    (tmp_path / "deploy").mkdir()
    betik = tmp_path / "deploy" / "guncelle.sh"
    betik.write_text("#!/bin/sh\necho ilk\n", encoding="utf-8")
    assert git("init", "-q").returncode == 0
    assert git("add", "-A").returncode == 0
    assert git("commit", "-qm", "ilk").returncode == 0

    # kiosk kullanıcısı betiği değiştirip COMMIT ETMEDEN stage eder (saldırı senaryosu)
    betik.write_text("#!/bin/sh\necho ele-gecirildi\n", encoding="utf-8")
    assert git("add", "deploy/guncelle.sh").returncode == 0

    eski_kapi = git("diff", "--quiet", "--", "deploy/guncelle.sh")
    yeni_kapi = git("status", "--porcelain", "--", "deploy/guncelle.sh")
    assert eski_kapi.returncode == 0, "beklenen: diff --quiet staged değişikliği GÖRMEZ"
    assert yeni_kapi.stdout.strip(), "status --porcelain staged değişikliği göstermeli"


def test_cloudwatch_arn_calisma_agacina_yazilmaz():
    """Bulgu 4: SNS ARN (hesap kimliği) depo ağacına yazılmamalı."""
    metin = (DEPO / "deploy" / "cloudwatch" / "alarmlar.sh").read_text(encoding="utf-8")
    assert 'ARN_DOSYASI="$HERE/.sns-arn"' not in metin, "ARN yine çalışma ağacına yazılıyor"
    assert "/.local/state" in metin or "XDG_STATE_HOME" in metin


def test_kiosk_birimi_ev_dizini_yazimlarini_acar():
    """Bulgu 5 (bilgi): Qt/Chromium $HOME altına yazar; ProtectHome=read-only bunu kesmemeli."""
    metin = (DEPO / "deploy" / "systemd" / "yourkiosk-kiosk.service").read_text(encoding="utf-8")
    assert "ProtectHome=read-only" in metin
    rw = [s for s in metin.splitlines() if s.strip().startswith("ReadWritePaths=")]
    assert rw, "ReadWritePaths yok"
    assert any("/home/kiosk/.cache" in s for s in rw), "HOME önbellek dizini yazılabilir değil"


def test_deploy_readme_tum_dizineri_listeler():
    """KEŞFEDİLEBİLİRLİK: deploy/README.md her alt dizini ve betiği bağlantılamalı.

    Bulgu (kullanıcı geri bildirimi): `alarmlar.sh`/`geri_donme.sh` depoda vardı ama kimse
    nereden başlayacağını bilemiyordu — belgeler yalnız kendi dizinlerinde duruyordu.
    """
    deploy = DEPO / "deploy"
    readme = (deploy / "README.md").read_text(encoding="utf-8")
    eksik = []
    for oge in sorted(deploy.iterdir()):
        if oge.name in {"README.md"}:
            continue
        hedef = f"{oge.name}/" if oge.is_dir() else oge.name
        if hedef not in readme:
            eksik.append(hedef)
    assert not eksik, f"deploy/README.md bunları listelemiyor: {eksik}"


def test_kok_readme_deploy_dizinine_baglanti_verir():
    """Kök README 'Ne var?' tablosunda deploy/ satırı olmalı (tek giriş noktası)."""
    kok = (DEPO / "README.md").read_text(encoding="utf-8")
    assert "deploy/README.md" in kok, "kök README deploy/ dizinini göstermiyor"


# --- i5 bulguları (25.10 19:18) -------------------------------------------------

def test_cihaz_ekle_belgelenen_silme_bicimini_kabul_eder():
    """Bulgu: belge `cihaz-ekle.sh C1 --sil` diyordu ama komut eşleşmiyordu.

    `--sil` yalnız 1. argüman olarak ele alınıyordu; `C1 --sil` biçimi `*)` dalına düşüp
    `ekle C1` çağırıyordu → cihaz SİLİNMİYOR, yeni parola üretilip yeniden ekleniyordu.
    Bu test iki biçimin de aynı işi yaptığını metin düzeyinde kilitler.
    """
    metin = (DEPO / "deploy" / "mosquitto" / "cihaz-ekle.sh").read_text(encoding="utf-8")
    assert '[[ "${2:-}" == "--sil" ]]' in metin, (
        "`<cihazId> --sil` biçimi ele alınmıyor (belgelenen silme komutu silmiyor)"
    )
    kullanim = metin.split("kullanım:", 1)[1][:200]
    assert "<cihazId> --sil" in kullanim, "kullanım satırı desteklenen biçimi göstermiyor"


# --- i5 bulgusu 3: imzasız `main` ucu çalıştırılmaz ------------------------------

def test_guncelleme_imzali_yayin_etiketinden_yapilir():
    """Bulgu 3 (26 Ekim i5): `git pull --ff-only` imzasız main ucunu çekip derliyordu.

    `main`'e yazma yetkisi olan ele geçirilmiş bir hesap/token 600 cihazda kod çalıştırabilirdi.
    Kural: güncelleme yalnız `yayin-*` desenli ANNOTATED + GPG imzalı etiketten yapılır,
    `git verify-tag` geçmezse derleme/çalıştırma YOK (fail-closed) ve günlüğe açık satır yazılır.
    """
    metin = _betik()
    # 1) imzasız uç çekme kalmadı
    kalan_pull = [
        s.strip()
        for s in metin.splitlines()
        if "git pull" in s and not s.strip().startswith("#")
    ]
    assert not kalan_pull, f"imzasız `git pull` hâlâ var: {kalan_pull}"

    # 2) imza kapısı: etiket deseni + verify-tag + annotated denetimi
    assert "yayin-*" in metin, "yayın etiketi deseni yok"
    assert "git verify-tag" in metin, "GPG imza doğrulaması yok (fail-open)"
    assert "cat-file -t" in metin, "annotated/hafif etiket ayrımı yapılmıyor"
    assert "git tag --merged origin/main" in metin, "etiket main'e ulaşıyor mu denetlenmiyor"
    assert "verify-tag -- " in metin or 'verify-tag -- "$ETIKET"' in metin

    # 3) doğrulama geçmezse çıkış kodu != 0 (fail-closed), sessiz atlama yok
    dogrula_govdesi = metin.split("etiket_dogrula()", 1)[1].split("\n}", 1)[0]
    assert "return 6" in dogrula_govdesi, "imza kapısı hata kodu döndürmüyor"
    assert "REDDEDİLDİ" in dogrula_govdesi or "güncelleme yapılmadı" in dogrula_govdesi, \
        "imza yokken günlüğe açık RED satırı yazılmıyor"
    assert "exit 6" in metin, "imza kapısı geçmezse betik durmuyor (fail-closed değil)"

    # 4) güncelleme etiketin commit'ine geçer (uçtan uca)
    assert 'checkout --detach --force "$ETIKET"' in metin, "güncelleme etiketten checkout yapmıyor"

    # 5) --kuru modda uyarı var, gerçek koşuda reddet
    kuru_blogu = metin.split("if [[ $KURU -eq 1 ]]", 1)[1].split("fi", 1)[0]
    assert "etiket_dogrula" in kuru_blogu and "ATLANIR" in kuru_blogu, \
        "--kuru imza kapısını denetlemiyor/uyarmıyor"

    # 6) anahtar kurulumu belgede (tek adım) — operatör ne yapacağını görebilmeli
    assert "gpg --import" in metin, "GPG anahtarı kurulum adımı betikte yazmıyor"
