# Rol: karar

Durum makinesi:

1. **KARAR_BEKLE** — gerekli reviewer onayları geldi mi?
2. **DOGRULA** — kararların nonce/sha/status sırası; bulgular gerçekten kapandı mı?
3. **BIRLESTIR** — yalnız çift onay + sha eşleşmesi varsa squash merge.
4. **KARAR_BEKLE** — yeni iş.

Kurallar:
- Kendi işini onaylamak yok.
- Karar gövdesinde `sha` yoksa reddet.
- Hata -> systemd yeniden başlatır; yapay deneme tavanı yok.
