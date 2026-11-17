#!/usr/bin/env python3
"""Lint an IAM policy JSON against AWS's own action list before pasting it into the console.

Catches the failures that make IAM refuse to save a policy:
  * unknown top-level / statement keys (e.g. a "_aciklama" comment block)
  * action names that do not exist (s3:HeadObject, s3:PutBucketLifecycleConfiguration, ...)
  * ARNs with placeholders or a wrong segment layout (S3 has no account segment)

Usage:  ./iam-policy-lint.py [policy.json]     (network required; exits 2 on problems)
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

KAYNAK = "https://awspolicygen.s3.amazonaws.com/js/policies.js"
IZINLI_IFADE = {
    "Sid", "Effect", "Action", "NotAction", "Resource", "NotResource",
    "Condition", "Principal", "NotPrincipal",
}


def servis_listesi() -> dict[str, set[str]]:
    ham = urllib.request.urlopen(KAYNAK, timeout=60).read().decode("utf-8", "ignore")
    # dosya "callback({...});" biciminde gelir
    govde = ham.split("=", 1)[1].strip().rstrip(";")
    sm = json.loads(govde)["serviceMap"]
    # TAM servis adi eslesmesi sart: "Amazon S3" oneki "Amazon S3 Files"i da yakalar.
    return {s["StringPrefix"]: set(s["Actions"]) for s in sm.values()}


def denetle(yol: Path) -> int:
    sorun = 0
    try:
        belge = json.loads(yol.read_text(encoding="utf-8"))
    except ValueError as hata:
        print(f"X JSON gecersiz: {hata}")
        return 1

    fazla = set(belge) - {"Version", "Statement", "Id"}
    if fazla:
        print(f"X ust duzeyde IAM'in tanimadigi alan(lar): {sorted(fazla)} - yorum alani koymayin")
        sorun += 1

    mevcut = servis_listesi()
    ifadeler = belge.get("Statement", [])
    if isinstance(ifadeler, dict):
        ifadeler = [ifadeler]

    for i, ifade in enumerate(ifadeler, 1):
        kim = ifade.get("Sid", f"#{i}")
        bilinmeyen = set(ifade) - IZINLI_IFADE
        if bilinmeyen:
            print(f"X [{kim}] taninmayan alan: {sorted(bilinmeyen)}")
            sorun += 1
        if ifade.get("Effect") not in ("Allow", "Deny"):
            print(f"X [{kim}] Effect 'Allow'/'Deny' olmali")
            sorun += 1

        aksiyonlar = ifade.get("Action", [])
        aksiyonlar = [aksiyonlar] if isinstance(aksiyonlar, str) else aksiyonlar
        for aksiyon in aksiyonlar:
            if ":" not in aksiyon:
                print(f"X [{kim}] bicim 'servis:Aksiyon' degil: {aksiyon}")
                sorun += 1
                continue
            servis, ad = aksiyon.split(":", 1)
            if servis not in mevcut:
                print(f"X [{kim}] bilinmeyen servis oneki: {servis}")
                sorun += 1
            elif ad != "*" and ad not in mevcut[servis]:
                print(f"X [{kim}] gecersiz aksiyon: {aksiyon}")
                sorun += 1

        kaynaklar = ifade.get("Resource", [])
        kaynaklar = [kaynaklar] if isinstance(kaynaklar, str) else kaynaklar
        for arn in kaynaklar:
            if arn == "*":
                continue
            if not arn.startswith("arn:aws:"):
                print(f"X [{kim}] ARN degil: {arn}")
                sorun += 1
                continue
            parca = arn.split(":")
            servis = parca[2] if len(parca) > 2 else ""
            hesap = parca[4] if len(parca) > 4 else ""
            if servis == "s3" and hesap:
                print(f"X [{kim}] S3 ARN'inde hesap alani bos olmali: {arn}")
                sorun += 1
            if servis == "iam" and not (hesap == "*" or re.fullmatch(r"\d{12}", hesap)):
                print(f"X [{kim}] IAM ARN'inde hesap 12 hane ya da '*' olmali: {arn}")
                sorun += 1

    if sorun == 0:
        print(f"OK {yol.name}: {len(ifadeler)} ifade, tum aksiyonlar gecerli")
    return 0 if sorun == 0 else 2


if __name__ == "__main__":
    hedef = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("policy.json")
    raise SystemExit(denetle(hedef))
