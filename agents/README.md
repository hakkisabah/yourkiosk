# agents — DSH çoklu ajan sistemi

Projeden bağımsız, N ajanlı geliştirme sistemi. DSH (deepseek-harness) üzerinde çalışır.

## Hızlı başlangıç (3 ajan)

1. Config oluştur (`agents/config/instance.example.toml` örnek):
   - `instance`, `repo`, `base_branch`
   - `dsh_profile` (ör. `headless`)
   - Her ajan için `token_file` (0600, repo dışı)
2. Doctor:
   ```bash
   ./agents/bin/agents --config agents/config/<instance>.toml doctor
   ```
3. Tek tur denemeleri:
   ```bash
   ./agents/bin/agents --config ... run --role developer --gorev "küçük bir görev"
   ./agents/bin/agents --config ... run --role reviewer
   ./agents/bin/agents --config ... run --role decision
   ```
4. systemd (gerçek kurulum; kullanıcı çalıştırır):
   ```bash
   ./agents/bin/agents --config ... install
   systemctl --user daemon-reload
   systemctl --user enable --now \
     agents@<instance>-developer.service \
     agents@<instance>-reviewer.service \
     agents@<instance>-decision.service
   ```

## 1 ajan modu

Config'te tek `[[agents]]` (developer). Ajan görevi yapar, PR açar ve **kendi PR'ını
squash-merge** eder; insan beklemez. Dal koruması review istiyorsa bu mod uyumsuzdur.

## Roller

| Rol | Yapar | Bekleme |
|---|---|---|
| developer | görev/ret → DSH → commit → push → PR | karar gelene kadar systemd servisi |
| reviewer | yeni head → diff → `KARAR_JSON` + nonce → status | yeni head |
| decision | çift onay → sha doğrula → squash merge | onaylar |

## Yol politikası

- Kodda sabit `/home`, `yourkiosk`, `otonom` yok; config/XDG.
- `AGENTS_CONFIG`, `AGENTS_STATE`, `AGENTS_SKILLS` ile override.
- Systemd birimleri `agents@<instance>-<role>.service` (kurulumda üretilir).

## Güvenlik

Bkz. `security/`. Özet: token makine/rol başına ayrı; reviewer/decision fail-closed;
karar stdout + nonce + zorunlu sha; sır repo dışı.
