# systemd dayanıklılığı (ders)

Amaç: insan müdahalesi olmadan hata sonrası kaldığı yerden devam.

- `Restart=on-failure`, `RestartSec=5`, `StartLimitIntervalSec=0`.
- `OnFailure=agents-notify@...` (gözlem).
- Durum dosyası atomik; süreç yeniden başlayınca aynı durumdan devam.
- Kilit: aynı instance+rol için tek süreç.
- Kota/süre tavanı yok; gerçek engel varsa açık hata + journal.
