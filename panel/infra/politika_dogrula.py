#!/usr/bin/env python3
"""IAM politikasını AWS'nin RESMÎ aksiyon listesine göre doğrular (ağ gerekir).

Neden: IAM konsolu politikayı kaydederken hataları tek tek söyler ama biz **önceden** yakalamak
istiyoruz. Bu betik:
  1. JSON'un yapısını denetler (yalnız Version/Statement; her ifadede Sid/Effect/Action/Resource),
  2. her `servis:Aksiyon` gerçekten var mı (AWS politika üreticisinin listesi),
  3. ARN biçimlerini kabaca denetler (S3 ARN'inde hesap olmaz; IAM ARN'inde 12 hane ya da `*`).

Kullanım:
    ./panel/infra/politika_dogrula.py                     # varsayılan: kurulum-politikasi.json
    ./panel/infra/politika_dogrula.py panel/infra/iam-policy.json
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

KAYNAK = "https://awspolicygen.s3.amazonaws.com/js/policies.js"
IZINLI_IFADE_ALANLARI = {"Sid", "Effect", "Action", "NotAction", "Resource", "NotResource", "Condition", "Principal", "NotPrincipal"}


def servis_listesi() -> dict[str, set[str]]:
    ham = urllib.request.urlopen(KAYNAK, timeout=60).read().decode("utf-8", "ignore")
    sm = json.loads(ham.split("=", 1)[1].strip().rstrip(";"))["serviceMap"]
    return {s["StringPrefix"]: set(s["Actions"]) for s in sm.values()}


def denetle(yol: Path) -> int:
    sorun = 0
    try:
        belge = json.loads(yol.read_text(encoding="utf-8"))
    except ValueError as hata:
        print(f"✗ JSON geçersiz: {hata}")
        return 1

    fazla = set(belge) - {"Version", "Statement", "Id"}
    if fazla:
        print(f"✗ Üst düzeyde IAM'in tanımadığı alan(lar): {sorted(fazla)}  (yorum alanı koymayın!)")
        sorun += 1

    mevcut = servis_listesi()
    ifadeler = belge.get("Statement", [])
    if isinstance(ifadeler, dict):
        ifadeler = [ifadeler]

    for i, ifade in enumerate(ifadeler, 1):
        kim = ifade.get("Sid", f"#{i}")
        bilinmeyen = set(ifade) - IZINLI_IFADE_ALANLARI
        if bilinmeyen:
            print(f"✗ [{kim}] tanınmayan alan: {sorted(bilinmeyen)}")
            sorun += 1
        if ifade.get("Effect") not in ("Allow", "Deny"):
            print(f"✗ [{kim}] Effect 'Allow'/'Deny' olmalı")
            sorun += 1

        aksiyonlar = ifade.get("Action", [])
        aksiyonlar = [aksiyonlar] if isinstance(aksiyonlar, str) else aksiyonlar
        for aksiyon in aksiyonlar:
            if ":" not in aksiyon:
                print(f"✗ [{kim}] aksiyon biçimi 'servis:Aksiyon' değil: {aksiyon}")
                sorun += 1
                continue
            servis, ad = aksiyon.split(":", 1)
            if servis not in mevcut:
                print(f"✗ [{kim}] bilinmeyen servis öneki: {servis}")
                sorun += 1
            elif ad != "*" and ad not in mevcut[servis]:
                print(f"✗ [{kim}] geçersiz aksiyon: {aksiyon}")
                sorun += 1

        kaynaklar = ifade.get("Resource", [])
        kaynaklar = [kaynaklar] if isinstance(kaynaklar, str) else kaynaklar
        for arn in kaynaklar:
            if arn == "*":
                continue
            if not arn.startswith("arn:aws:"):
                print(f"✗ [{kim}] ARN değil: {arn}")
                sorun += 1
                continue
            parca = arn.split(":")
            servis = parca[2] if len(parca) > 2 else ""
            hesap = parca[4] if len(parca) > 4 else ""
            if servis == "s3" and hesap:
                print(f"✗ [{kim}] S3 ARN'inde hesap alanı boş olmalı: {arn}")
                sorun += 1
            if servis == "iam" and not (hesap == "*" or re.fullmatch(r"\d{12}", hesap)):
                print(f"✗ [{kim}] IAM ARN'inde hesap 12 hane ya da '*' olmalı: {arn}")
                sorun += 1

    if sorun == 0:
        print(f"✓ {yol.name}: {len(ifadeler)} ifade, tüm aksiyonlar geçerli")
    return 0 if sorun == 0 else 2


if __name__ == "__main__":
    hedef = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("kurulum-politikasi.json")
    raise SystemExit(denetle(hedef))
