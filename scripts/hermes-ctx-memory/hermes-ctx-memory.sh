#!/usr/bin/env bash
set -euo pipefail

# Kullanım ve yardım mesajını basan fonksiyon
show_usage() {
    cat <<'EOF'

📌 KULLANIM ÖRNEKLERİ:

  1. Yerel Dosya Olarak Kullanım:
     ./hermes-setup.sh                 # Varsayılan 'developer' profiline uygular
     ./hermes-setup.sh <profil_adi>    # Belirtilen profile uygular (ör: ./hermes-setup.sh work)
     ./hermes-setup.sh --help          # Bu yardım mesajını gösterir

  2. GitHub Gist (curl) ile Tek Satırda Kullanım:
     # Varsayılan 'developer' profili için:
     curl -fsSL "https://gist.githubusercontent.com/hakkisabah/dd8d579c2db233be982926ae53021a28/raw/hermes-ctx-memory.sh" | bash

     # Farklı bir profil için (örneğin 'research' profili):
     curl -fsSL "https://gist.githubusercontent.com/hakkisabah/dd8d579c2db233be982926ae53021a28/raw/hermes-ctx-memory.sh" | bash -s -- research

EOF
}

# --help veya -h parametresi verildiyse yardım göster ve çık
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    show_usage
    exit 0
fi

# Kullanıcı parametre girdi mi kontrol et (sonradan örnek göstermek için)
NO_ARG_GIVEN=false
if [[ $# -eq 0 ]]; then
    NO_ARG_GIVEN=true
fi

PROFILE="${1:-developer}"

# 1. Ön Kontrol: Hermes yüklü mü?
if ! command -v hermes >/dev/null 2>&1; then
    echo "❌ HATA: 'hermes' komutu sistemde bulunamadı. Lütfen önce Hermes Agent'ı kurun." >&2
    exit 1
fi

# 2. Ön Kontrol: Profil klasörü mevcut mu? (default hariç)
if [[ "$PROFILE" != "default" && ! -d "$HOME/.hermes/profiles/$PROFILE" ]]; then
    echo "❌ HATA: '$PROFILE' profili bulunamadı (~/.hermes/profiles/$PROFILE yok)." >&2
    echo "💡 Önce 'hermes profile create $PROFILE' komutuyla profili oluşturun." >&2
    exit 1
fi

echo "⚙️  '$PROFILE' profili için bellek ve bağlam ayarları uygulanıyor..."

# Model ve Bağlam Penceresi (Context) Ayarları
hermes -p "$PROFILE" config set model.context_length 131072
hermes -p "$PROFILE" config set model.ollama_num_ctx 65536

# Otomatik Geçmiş Sıkıştırma (Compression) Ayarları
hermes -p "$PROFILE" config set compression.enabled true
hermes -p "$PROFILE" config set compression.threshold 0.50
hermes -p "$PROFILE" config set compression.target_ratio 0.20
hermes -p "$PROFILE" config set compression.protect_last_n 20

# Kalıcı Bellek (Memory) Ayarları
hermes -p "$PROFILE" config set memory.memory_enabled true
hermes -p "$PROFILE" config set memory.user_profile_enabled true
hermes -p "$PROFILE" config set memory.memory_char_limit 3500
hermes -p "$PROFILE" config set memory.user_char_limit 2500

echo "✅ Tüm ayarlar '$PROFILE' profiline başarıyla uygulandı!"
echo "🔄 Değişikliklerin aktif olması için çalışan '$PROFILE' oturumunu yeniden başlatın."

# Eğer kullanıcı profil adı girmeden çalıştırdıysa (varsayılan 'developer' kullanıldıysa) örnekleri göster
if [[ "$NO_ARG_GIVEN" == true ]]; then
    echo ""
    echo "ℹ️  Profil belirtilmediği için varsayılan 'developer' profili güncellendi."
    echo "💡 Farklı bir profili güncellemek isterseniz aşağıdaki örnekleri kullanabilirsiniz:"
    show_usage
fi
