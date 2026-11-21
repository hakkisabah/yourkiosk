# agents — DSH çoklu ajan sistemi

Projeden bağımsız, N ajanlı geliştirme sistemi. DSH (deepseek-harness) üzerinde çalışır.

## Ön koşullar

Temiz makinede `doctor` eksikleri söyler; bkz. `install/ON-KOSULLAR.md`.

## Sıfırdan kurulum

```bash
python3 agents/install/wizard.py
```

Sihirbaz instance/repo/N ajan bilgilerini sorar; config ve makine betiklerini üretir.

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

## Eksik rollü modlar

Kapı (i5 incelemesi + i3 kararı) config'teki ajan sayısından bağımsız olarak zorunludur; eksik rol
PR'ı birleştirmez, `karar` bekler:

- **1 ajan (developer):** görevi uygular, dalına push eder, PR açar ve **karar bekler**. Yalnız
  geliştirme/deneme içindir; PR birleşmez.
- **2 ajan (developer + decision):** decision inceleme durumu `success` olmadan merge etmez;
  reviewer yoksa PR onay bekler.
- **3 ajan (developer + reviewer + decision):** tam kapı; varsayılan kurulum.

`agents doctor` eksik kapı rollerini uyarı olarak basar, `roles.py` aynı kuralı çalışma anında
uygular (fail-closed).

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
