# Sandbox kaçışları (ders)

- `.git` ayrı rw mount; `.git/hooks`, `.git/config` ro.
- Gölge HOME; token/.ssh/aws ro veya gizli.
- `/run` maskeli; user systemd/D-Bus yok; `--unshare-net`.
- FD geçişi yok; `/proc` izole; `--die-with-parent`.
- `.git/info/{attributes,exclude,grafts}` düzenli dosya mı (FIFO/symlink reddi).
- Diff/commit/çıktı bayt sınırlı; sınır aşımında süreç öldürülür.
