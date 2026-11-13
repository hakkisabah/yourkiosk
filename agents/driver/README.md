# driver

DSH sürücüsü. Kurallar:
- Sabit yol adı yok; tüm yollar config/XDG.
- Kota/süre sınırı yok; dayanıklılık systemd `Restart=on-failure`.
- Durum `state.py`; birim `systemd.py`.

Komutlar (hedef):
```
agents doctor
agents run --role developer
agents status
agents install
agents uninstall
```
