# agents kurulum runbook'u (3 makine)

Amaç: **aceri5 = developer**, **i5 = reviewer**, **i3 = decision**. Her makinede tek rol.

## 0. Ortak hazırlık

- DSH checkout: `~/deepseek-harness` (node, bin.js).
- Repo dalı: `temizlik/sifirdan-ajan-sistemi`.
- Token dosyaları **0600**, dizin **0700**, repo dışı.
- DSH `.env` içinde geçerli `DEEPSEEK_API_KEY`.

## 1. aceri5 (developer)

```bash
systemctl --user disable --now \
  agents@agents-test-reviewer.service agents@agents-test-decision.service

cd /home/hakki/evrim_otonom/yourkiosk
./agents/bin/agents --config agents/config/agents-test.toml install --role developer
systemctl --user daemon-reload
systemctl --user enable --now agents@agents-test-developer.service
systemctl --user list-units 'agents@*' --no-pager
```
Beklenen: yalnız developer aktif.

## 2. i5 (reviewer)

1. Repoyu güncelle:
   ```bash
   cd ~/projeler/yourkiosk
   git fetch origin
   git checkout -f -B temizlik/sifirdan-ajan-sistemi origin/temizlik/sifirdan-ajan-sistemi
   ```
2. Token: aceri5'ten kopyala (veya i5'te oluştur):
   ```bash
   mkdir -p ~/.config/yourkiosk-secrets/agents-test
   chmod 700 ~/.config/yourkiosk-secrets/agents-test
   # aceri5'ten (i5'te çalıştır):
   scp hakki@192.168.1.51:~/.config/yourkiosk-secrets/agents-test/inceleme.token \
       ~/.config/yourkiosk-secrets/agents-test/inceleme.token
   chmod 600 ~/.config/yourkiosk-secrets/agents-test/inceleme.token
   ```
3. Model overlay:
   ```bash
   mkdir -p ~/.dsh
   cp agents/install/dsh-overlay-lite.example.yml ~/.dsh/agents-overlay-lite.yml
   ```
4. Kur:
   ```bash
   ./agents/bin/agents --config agents/config/makine-i5.example.toml doctor
   ./agents/bin/agents --config agents/config/makine-i5.example.toml install
   systemctl --user daemon-reload
   systemctl --user enable --now agents@agents-test-reviewer.service
   systemctl --user status agents@agents-test-reviewer.service --no-pager | head -5
   ```
5. Test: aceri5'te bir PR aç; i5 logunda `inceleme: #N ...` görünmeli.

## 3. i3 (decision)

1. Repo/token aynı şekilde (token: `karar.token`).
2. DSH gerekmez; yalnız GitHub API.
3. Kur:
   ```bash
   ./agents/bin/agents --config agents/config/makine-i3.example.toml doctor
   ./agents/bin/agents --config agents/config/makine-i3.example.toml install
   systemctl --user daemon-reload
   systemctl --user enable --now agents@agents-test-decision.service
   ```

## 4. Dayanıklılık testi

```bash
systemctl --user kill --signal=KILL agents@agents-test-developer.service
sleep 10
systemctl --user status agents@agents-test-developer.service --no-pager | head -4
```
Beklenen: `Restart=always` ile yeniden `active (running)`.

## 5. Kontrol listesi

- aceri5: yalnız developer.
- i5: yalnız reviewer; token 0600.
- i3: yalnız decision; token 0600.
- Hiçbir makinede `otonom-*` / `yourkiosk-nobetci` yok.
