# DSH uyarlama uyarısı

Bu skill Hermes'ten olduğu gibi taşındı. Gövdesinde DSH'de birebir karşılığı
olmayan araç veya yollar var:

- Hermes dizin yolu

Eşleme tablosu:

| Hermes | DSH |
|---|---|
| `hermes chat --oneshot` | `pnpm dsh headless` (yerel checkout) |
| `write_file` / `read_file` / `patch` | `write` / `read` / `edit` |
| `terminal` / `bash` | `bash` |
| `browser_exec` | `web_fetch`, `web_search` veya `curl` |
| `~/.hermes/...` | `~/.agents/...` veya depo yolu |
| `skill_manage` | Elle `SKILL.md` düzenleme |

Gövde Faz 5'te DSH araçlarına uyarlanacak. O zamana kadar bu skill'i
yüklerken yukarıdaki karşılıkları kullan.
