# agents kurulum runbook'u

## 1. Sihirbaz (önerilen)

Repo kökünde:

```bash
python3 agents/install/wizard.py
```

Sorular: instance adı, GitHub repo, ajan sayısı (1..N), her ajan için ad/makine/token adı.
Sihirbaz:
- `agents/config/<instance>.toml` üretir,
- her makine için `agents/install/agents-kur-<makine>.sh` üretir,
- token yollarını `$HOME/.config/<instance>/<token>` olarak yazar.

## 2. Token

Her ajan/makine için ayrı fine-grained token:
- Contents: Read and write
- Metadata: Read-only
- Pull requests: Read and write (developer/decision)
- Commit statuses: Read and write (reviewer/decision)
- Issues: Read-only

Dosya `0600`, dizin `0700`.

## 3. Her makinede

1. Repoyu kopyala (dal: `temizlik/sifirdan-ajan-sistemi`).
2. Token dosyasını `$HOME/.config/<instance>/<token>` yoluna koy.
3. `bash agents/install/agents-kur-<makine>.sh`
4. `systemctl --user list-units 'agents@*' --no-pager`

## 4. Görev

- GitHub issues: `agents/gorev` etiketi.
- veya yerel: `$HOME/.local/state/agents/<instance>/gorevler/*.md`.

Developer görevi alır, PR açar; reviewer inceler; decision merge eder.
