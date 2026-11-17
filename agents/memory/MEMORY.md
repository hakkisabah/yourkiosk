# Kalıcı dersler

- Karar kanalı: stdout + nonce; dosya kanalı kullanma.
- Status listesi en yeniden eskiye gelir; aynı context'te İLK kayıt geçerli.
- Diff/commit/ajan çıktısı bayt sınırıyla okunur; aşımda fail-closed.
- Sandbox: gölge HOME, repo ro, ağ kapalı, `.git/info` ro, FD yok.
- Token: makine/rol başına ayrı; kapı token'ı ajanlara verilmez.
- systemd: Restart=on-failure, StartLimitIntervalSec=0, OnFailure=.
