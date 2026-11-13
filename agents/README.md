# agents — DSH çoklu ajan sistemi

Projeden bağımsız, N ajanlı geliştirme sistemi. DSH (deepseek-harness) üzerinde çalışır.
Hermes veya eski `otomasyon/` kodu **kullanılmaz**; yalnız dersler `playbooks/` altındadır.

## N seçimi

- **1 ajan:** geliştirici + test + kendi PR'ını squash merge. İnsan beklemez.
  Dal koruması review istiyorsa bu mod uyumsuzdur; N>=2 kullan.
- **N>=2:** geliştirici, reviewer(lar), karar. Roller ayrı makinelerde olabilir.
  Karar, gerekli onaylar gelmeden merge etmez.

Bizim kurulum: **N=3** (aceri5 geliştirici, i5 reviewer, i3 karar).

## Kurulum

```bash
agents/install/install.sh --config ~/.config/agents/<instance>.toml
agents doctor --config ~/.config/agents/<instance>.toml
agents install --role developer --machine aceri5
```

Ayrıntı: `install/`, `config/instance.example.toml`.

## Yapı

| Dizin | İçerik |
|---|---|
| `config/` | örnek instance; sabit yol yok |
| `driver/` | DSH sürücüsü, durum makinesi, GitHub, systemd |
| `roles/` | geliştirici / reviewer / karar talimatları |
| `memory/` | kısa kullanıcı ve kalıcı dersler |
| `skills/` | INDEX + SKILL.md (gövde tembel yüklenir) |
| `playbooks/` | eski sistemden çıkarılan tasarım dersleri |
| `security/` | tehdit modeli, sandbox, token kapsamları |
| `install/` | kurulum ve systemd şablonları |

## İlkeler

1. Yapay kota/süre sınırı yok; dayanıklılık systemd `Restart=on-failure` ile.
2. Sabit yol adı yok; her şey instance/config/XDG.
3. Skill'ler hafızaya gömülmez; yalnız INDEX görünür, gövde `skill` çağrısında.
4. Karar: stdout + nonce + zorunlu sha; fail-closed.
