#!/usr/bin/env python3
"""Çözüm A: cihazlar `kiosk/*` önekinden okusun (CloudFront + OAC + kova politikası).

NE YAPAR (sırayla, her adımı yazdırır):
  1. AWS kimliğini ve veri dağıtımını bulur (alan adından).
  2. Kova politikasını okur; `kiosk/*` için CloudFront OAC izni YOKSA ekler (mevcut ifadeler korunur).
  3. `kiosk/` altında eksik veri dosyalarını kökten kopyalar (lastupdate/lastSystemData/match/…).
  4. `https://<dağıtım>/kiosk/match.json` erişimini doğrular (200 beklenir).

    ./panel/infra/onek_gecis.py                       # yalnız plan (hiçbir şey değiştirmez)
    ./panel/infra/onek_gecis.py --uygula              # politikayı yaz + dosyaları kopyala
    ./panel/infra/onek_gecis.py --uygula --sadece-politika

Cihaz tarafı (en son, elle): `push_ayarla.py --veri-adresi https://<dağıtım>/kiosk/`
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request

COGRAFYA = "eu-central-1"
VERI_DOSYALARI = ("lastupdate.json", "lastSystemData.json", "match.json", "makinebilgileri.json", "sablon.json", "ayarlar.json")


def aws(*arg: str) -> tuple[int, str, str]:
    r = subprocess.run(["aws", *arg], capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def politika_ekle(politika: dict, kova: str, onek: str, dagitim_arn: str) -> bool:
    """`onek*` için CloudFront OAC izni yoksa ekler; eklendiyse True döner."""
    ifadeler = politika.setdefault("Statement", [])
    for i in ifadeler:
        if i.get("Principal", {}).get("Service") != "cloudfront.amazonaws.com":
            continue
        kaynaklar = i.get("Resource") if isinstance(i.get("Resource"), list) else [i.get("Resource")]
        if any(str(k) in (f"arn:aws:s3:::{kova}/{onek}*", f"arn:aws:s3:::{kova}/*") for k in kaynaklar if k):
            return False
    # aynı Sid iki kez olamaz → eski kiosk ifadesini kaldır
    politika["Statement"] = [x for x in ifadeler if x.get("Sid") != "KioskOnekOAC"]
    ifadeler = politika["Statement"]
    ifadeler.append({
        "Sid": "KioskOnekOAC",
        "Effect": "Allow",
        "Principal": {"Service": "cloudfront.amazonaws.com"},
        "Action": "s3:GetObject",
        "Resource": f"arn:aws:s3:::{kova}/{onek}*",
        "Condition": {"StringEquals": {"AWS:SourceArn": dagitim_arn}},
    })
    return True


def _head(url: str) -> str:
    try:
        istek = urllib.request.Request(url, method="HEAD", headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(istek, timeout=12) as y:
            return f"HTTP {y.status}"
    except urllib.error.HTTPError as h:
        return f"HTTP {h.code}"
    except Exception as h:  # noqa: BLE001
        return f"hata: {type(h).__name__}"


def _dagitim_teshisi(kova: str, dagitim_id: str) -> None:
    """Origin/behavior/OAC ve nesne erişimini GERÇEKLERE göre yazdırır (tahmin yok)."""
    print("\n--- dağıtım yapılandırması ---")
    kod, cikti, hata = aws("cloudfront", "get-distribution-config", "--id", dagitim_id, "--output", "json")
    if kod != 0:
        print(f"  ✗ okunamadı: {hata}")
        return
    cfg = json.loads(cikti).get("DistributionConfig", {})
    origins = cfg.get("Origins", {}).get("Items", [])
    for o in origins:
        s3 = o.get("S3OriginConfig") or {}
        print(f"  origin {o.get('Id')}: {o.get('DomainName')}  originPath={o.get('OriginPath') or '-'}")
        print(f"     OAC={o.get('OriginAccessControlId') or '(yok)'} · OAI={s3.get('OriginAccessIdentity') or '(yok)'}")

    # OAC ayarları (imza davranışı yanlışsa 403 sürer)
    for o in origins:
        oac_id = o.get("OriginAccessControlId")
        if not oac_id:
            continue
        kod3, cikti3, hata3 = aws("cloudfront", "get-origin-access-control", "--id", oac_id, "--output", "json")
        if kod3 == 0:
            oc = json.loads(cikti3).get("OriginAccessControl", {}).get("OriginAccessControlConfig", {})
            print(f"     OAC ayarı: behaviour={oc.get('SigningBehavior')} · protokol={oc.get('SigningProtocol')} "
                  f"· tür={oc.get('OriginAccessControlOriginType')}")
            if oc.get("SigningBehavior") == "never":
                print("     ✗ SigningBehavior=never → S3'e imzasız gider (403 nedeni)")
        else:
            print(f"     ✗ OAC okunamadı ({oac_id}): {hata3[:80]}")

    varsayilan = cfg.get("DefaultCacheBehavior", {}).get("TargetOriginId")
    print(f"  varsayılan behavior → origin: {varsayilan}")
    for b in cfg.get("CacheBehaviors", {}).get("Items", []):
        print(f"  behavior {b.get('PathPattern')} → origin: {b.get('TargetOriginId')}")

    if any("--" in str(o.get("OriginPath") or "") for o in origins):
        print("  ⚠ originPath ayarlı: istenen yol origin yoluna EKLENİR (403/404 nedeni olabilir)")

    print("\n--- nesne erişimi (doğrudan S3 vs CloudFront) ---")
    bolge = "eu-central-1"
    for anahtar in ("match.json", "kiosk/match.json"):
        s3_url = f"https://{kova}.s3.{bolge}.amazonaws.com/{anahtar}"
        print(f"  {anahtar:<22} S3: {_head(s3_url):<12}", end="")
        kod2, cikti2, _ = aws("s3api", "head-object", "--bucket", kova, "--key", anahtar,
                              "--query", "{boyut:ContentLength,acl:Grant}", "--output", "json")
        print(f"nesne: {'var' if kod2 == 0 else 'YOK/erişilemiyor'}")


def main() -> int:
    a = argparse.ArgumentParser(description="kiosk/* önekine geçiş (CloudFront OAC + kova politikası)")
    a.add_argument("--kova", default="yourkiosk-veri")
    a.add_argument("--alan-adi", default="d2dnrvsx5eevod.cloudfront.net", help="veri dağıtımının alan adı")
    a.add_argument("--onek", default="kiosk/")
    a.add_argument("--uygula", action="store_true", help="değişiklikleri yaz (varsayılan: yalnız plan)")
    a.add_argument("--sadece-politika", action="store_true", help="veri dosyalarını kopyalama")
    a.add_argument("--teshis", action="store_true", help="kova politikasındaki ifadeleri özetle ve çık")
    a.add_argument("--zorla-ekle", action="store_true", help="'zaten var' görünse de kiosk ifadesini ekle")
    secim = a.parse_args()

    kod, hesap, hata = aws("sts", "get-caller-identity", "--query", "Account", "--output", "text")
    if kod != 0:
        print(f"✗ AWS kimliği yok: {hata}", file=sys.stderr)
        return 2
    print(f"hesap           : {hesap}")

    kod, cikti, hata = aws(
        "cloudfront", "list-distributions",
        "--query", f"DistributionList.Items[?DomainName=='{secim.alan_adi}'].{{Id:Id,ARN:ARN}}",
        "--output", "json",
    )
    if kod != 0:
        print(f"✗ dağıtımlar okunamadı: {hata}", file=sys.stderr)
        return 2
    daagitimlar = json.loads(cikti or "[]")
    if not daagitimlar:
        print(f"✗ '{secim.alan_adi}' dağıtımı bulunamadı", file=sys.stderr)
        return 2
    dagitim = daagitimlar[0]
    print(f"dağıtım         : {dagitim['Id']}  ({dagitim['ARN']})")

    # ---- 1) kova politikası
    kod, politika_metni, hata = aws("s3api", "get-bucket-policy", "--bucket", secim.kova, "--query", "Policy", "--output", "text")
    if kod != 0:
        print(f"✗ kova politikası okunamadı: {hata}", file=sys.stderr)
        return 2
    politika = json.loads(politika_metni)
    ifadeler = politika.setdefault("Statement", [])
    kaynak = f"arn:aws:s3:::{secim.kova}/{secim.onek}*"

    if secim.teshis:
        print("\n--- kova politikası ifadeleri ---")
        for i, ifade in enumerate(ifadeler, 1):
            principal = ifade.get("Principal")
            if isinstance(principal, dict):
                principal = principal.get("Service") or principal.get("AWS") or principal.get("CanonicalUser")
            kosullar = ifade.get("Condition") or {}
            source_arn = ""
            for kural in kosullar.values():
                if isinstance(kural, dict) and "AWS:SourceArn" in kural:
                    source_arn = kural["AWS:SourceArn"]
            print(f"  {i}. Sid={ifade.get('Sid','-'):<24} {ifade.get('Effect','?'):<6} "
                  f"principal={principal} action={ifade.get('Action')}")
            print(f"     resource={ifade.get('Resource')}")
            if source_arn:
                print(f"     SourceArn={source_arn}{'  ← VERİ dağıtımı' if source_arn == dagitim['ARN'] else '  ← BAŞKA dağıtım!'}")
            if kosullar and not source_arn:
                print(f"     condition={json.dumps(kosullar, ensure_ascii=False)[:160]}")
        print("\n(Deny ifadeleri Allow'u EZER; kiosk/* için Deny varsa onu kaldırmadan çalışmaz.)")
        _dagitim_teshisi(secim.kova, dagitim["Id"])
        return 0
    eklendi = True if secim.zorla_ekle else politika_ekle(politika, secim.kova, secim.onek, dagitim["ARN"])
    if not eklendi:
        print(f"✓ kova politikası: '{secim.onek}*' için CloudFront izni zaten var")
    else:
        print(f"+ kova politikasına eklenecek: KioskOnekOAC → {kaynak}")
        if secim.uygula:
            with open("/tmp/kova-politika-yeni.json", "w", encoding="utf-8") as f:
                json.dump(politika, f, ensure_ascii=False, indent=2)
            kod, _, hata = aws("s3api", "put-bucket-policy", "--bucket", secim.kova,
                               "--policy", "file:///tmp/kova-politika-yeni.json")
            if kod != 0:
                print(f"✗ politika yazılamadı: {hata}", file=sys.stderr)
                return 2
            print("  ✓ politika yazıldı")

    # ---- 2) veri dosyalarını kökten kiosk/ altına kopyala
    if not secim.sadece_politika:
        kod, kok_liste, _ = aws("s3api", "list-objects-v2", "--bucket", secim.kova, "--query", "Contents[].Key", "--output", "json")
        kod2, onek_liste, _ = aws("s3api", "list-objects-v2", "--bucket", secim.kova, "--prefix", secim.onek,
                                  "--query", "Contents[].Key", "--output", "json")
        kok = set(json.loads(kok_liste or "[]"))
        onektekiler = set(json.loads(onek_liste or "[]"))
        for ad in VERI_DOSYALARI:
            hedef = f"{secim.onek}{ad}"
            if hedef in onektekiler:
                print(f"✓ {hedef} var")
                continue
            if ad not in kok:
                print(f"· {ad} kökte de yok (atlandı)")
                continue
            print(f"+ kopyalanacak: {ad} → {hedef}")
            if secim.uygula:
                kod, _, hata = aws("s3", "cp", f"s3://{secim.kova}/{ad}", f"s3://{secim.kova}/{hedef}",
                                   "--cache-control", "no-cache,must-revalidate", "--only-show-errors")
                if kod != 0:
                    print(f"  ✗ kopyalanamadı: {hata}", file=sys.stderr)
                else:
                    print("  ✓ kopyalandı")

    # ---- 3) doğrulama
    adres = f"https://{secim.alan_adi}/{secim.onek}match.json"
    try:
        istek = urllib.request.Request(adres, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(istek, timeout=15) as y:
            boyut = len(y.read())
        print(f"✓ {adres} → HTTP 200 · {boyut} bayt")
    except urllib.error.HTTPError as h:
        print(f"✗ {adres} → HTTP {h.code} (politika/kopyalama henüz uygulanmadıysa normaldir)")
    except Exception as h:  # noqa: BLE001
        print(f"✗ {adres} → {h}")

    if not secim.uygula:
        print("\n(plan) uygulamak için: --uygula")
    else:
        print("\nSIRADAKİ (cihaz): push_ayarla.py --veri-adresi https://%s/%s" % (secim.alan_adi, secim.onek))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
