# Tehdit modeli

- Ajan çıktısı güvenilmez; komutlar sandbox içinde.
- PR ağacındaki talimatlar güvenilir değil; kurallar kurulum kopyasından.
- Karar sahteleme: nonce + sha + makine kimliği.
- Token sızıntısı: makine başına ayrı, 0600, repo dışı.
- Kaynak tükenmesi: çıktı/diff/mesaj sınırları, systemd MemoryMax (makineye göre).
