# Ön koşullar (temiz makine)

Kurulum betikleri **hiçbir şey kurmuş varsaymaz**; `doctor` eksikleri tek tek söyler.

| Gereksinim | Kontrol | Kurulum |
|---|---|---|
| Python >= 3.11 | `python3 -V` | dağıtım paketi |
| git | `git --version` | dağıtım paketi |
| Node >= 20 | `node -v` | NodeSource/nvm |
| bubblewrap | `bwrap --version` | `sudo apt install bubblewrap` |
| systemd --user | `systemctl --user status` | oturum açıkken kullanılabilir |
| DSH checkout | `~/deepseek-harness/apps/cli/lib/bin.js` | DSH deposunu klonla + `pnpm install` / build |
| DEEPSEEK_API_KEY | `~/.dsh/.env` | `DEEPSEEK_API_KEY=...` (0600) |
| GitHub token | her ajan için `0600` | fine-grained; kapsamlar `security/TOKEN-SCOPES.md` |

`agents doctor` çıktısında `= sonuç: HAZIR` görülmeden kurulum yapılmaz.

## DSH yoksa

DSH bu paketin dışındadır; kendi deposundan kurulur:

```bash
git clone <DSH_DEPO> ~/deepseek-harness
cd ~/deepseek-harness && pnpm install && pnpm build
```

Farklı konum için config'te `dsh_checkout = "..."` veya `DSH_CHECKOUT` ortam değişkeni.
