# Cache Storage sözleşmeleri (ve taklit depoların katılaştırılması)

Tarayıcı tarafında disk önbelleği = **Cache Storage**. Aşağıdaki kurallar tarayıcıya özgüdür;
hand-rolled taklit depolar bunları uygulamadığı için iki hata ancak kullanıcının makinesinde
(konsolda) ortaya çıktı. **Kural: taklidi gerçek API'ye benzeterek katılaştır** — yoksa test yeşil,
cihaz boş.

## Sözleşme tablosu

| Çağrı | Gerçek davranış | Yapılacak |
|---|---|---|
| `cache.put(anahtar, yanıt)` | `anahtar` geçerli **http(s)** URL/Request olmalı | Sentetik ama geçerli URL üret: `new URL('__onbellek/veri/<ad>', location.origin)`. `meta:`/`gorsel:`/`app:` şemaları `Request scheme 'x' is unsupported` ile fırlatır |
| `cache.keys()` | **`Request[]`** döner (string değil!) | Karşılaştırmadan önce metne çevir: `typeof k === 'string' ? k : k.url` |
| `cache.match(k)` / `delete(k)` | Mutlak URL string'i ya da Request kabul eder | Normalize edilmiş metni ver |
| Bağlam | **Secure context** şart | `http://127.0.0.1` ve `localhost` güvenli sayılır; `file://` değil |
| Yanıt başlıkları | Özel başlıklar (`x-damga`, `x-url`, …) aynen saklanır | Meta veriyi (damga, son gösterim, sayaç) başlıkta tut; değeri gövdeden ayrı yazma |
| Gövde | `Response` gövdesi bir kez okunur | Her `put` için **taze** `Response` üret; tüketilmiş gövdeyi yeniden verme |

## Anahtar üretimi (tek yerden, dışa açık)

```ts
const ONEK = '__onbellek'
const VERI_YOLU = `${ONEK}/veri/`
const GORSEL_YOLU = `${ONEK}/gorsel/`
const META_YOLU = `${ONEK}/meta/lastupdate`

function anahtar(yol: string): string {
  const kok = globalThis.location?.origin || 'http://127.0.0.1'   // testte location yok
  return new URL(yol, `${kok}/`).toString()
}

// uzun adresleri (görsel URL'i) anahtara sığdır: kısa, eşzamanlı özet
function ozet(metin: string): string {
  let h = 5381
  for (let i = 0; i < metin.length; i += 1) h = ((h << 5) + h + metin.charCodeAt(i)) >>> 0
  return h.toString(16).padStart(8, '0')
}
const gorselAnahtari = (url: string) => anahtar(GORSEL_YOLU + ozet(url))

// dışa açık normalleştirici: hem string hem Request kabul eder
export function anahtarMetni(k: unknown): string {
  if (typeof k === 'string') return k
  const url = (k as { url?: unknown } | null)?.url
  return typeof url === 'string' ? url : String(k)
}
```

Görselin gerçek URL'i anahtardan türetilemezse **başlıkta** taşınsın (`x-url`), liste/temizlik
kodları adresi oradan okusun.

## Yazma asla gösterimi düşürmesin

```ts
async bagla(ad = ONBELLEK_ADI): Promise<boolean> {
  try {
    this.depo = await caches.open(ad)
    const deneme = anahtar(`${ONEK}/deneme`)          // gerçekten çalışıyor mu?
    await this.depo.put(deneme, new Response('ok'))
    await this.depo.match(deneme)
    await this.depo.delete(deneme)
    return true
  } catch (hata) {
    this.depo = null                                   // sessizce devre dışı
    console.warn('[uygulama] önbellek kullanılamıyor:', hata)
    return false
  }
}

private _kapat(hata: unknown) { this.depo = null; console.warn('...', hata) }

async veriYaz(...) {
  if (!this.depo) return
  try { await this.depo.put(anahtar(VERI_YOLU + ad), yeniYanit) }
  catch (hata) { this._kapat(hata) }                   // fırlatma: ekran çalışmaya devam etsin
}
```

Okuma yolları da (`veriOku`, `gorselOku`, `bakim`, `bosalt`) depo `null` iken **güvenli değer**
döndürmeli (`null` / `{silinen: 0}`), yoksa önbellek arızası veri yüklemeyi engeller.

## Taklit depoyu gerçek gibi katı yap (testte)

```ts
class SahteDepo {
  kayitlar = new Map<string, Yanit>()

  async put(sorgu: string, yanit: Yanit): Promise<void> {
    const sema = String(sorgu).split(':')[0]
    if (!/^https?$/.test(sema)) {
      throw new TypeError(`Failed to execute 'put' on 'Cache': Request scheme '${sema}' is unsupported`)
    }
    /* gövdeyi tüket + başlıkları sakla */
  }

  // gerçek tarayıcı gibi: Request benzeri nesneler döndür ({ url }), string DEĞİL
  async keys() { return [...this.kayitlar.keys()].map((k) => ({ url: k })) }
}
```

Bu iki satırlık katılık, iki gerçek hatayı da testte yakalar. Ayrıca davranışı doğrulayan testler:

* **Anahtar biçimi testi:** yazımdan sonra `depo.keys()` içindeki her anahtar `/^https?:\/\//`
  eşleşmeli ve beklenen yolları (`__onbellek/meta/lastupdate`, `…/veri/<ad>`, `…/gorsel/`) içermeli.
* **Bozuk depo testi:** `put` fırlatan bir depo ver → `damgaYaz`/`veriYaz` **resolve** etmeli,
  `etkin === false` olmalı, okuma yolları güvenli değer döndürmeli.

## Önbellek kuralları (yerel disk önbelleğiyle aynı olmalı)

| Kural | Uygulama |
|---|---|
| Geçersizleşme | Veri önbelleği `lastupdate` damgasına bağlı; damga değiştiyse kayıt kullanılmaz |
| Bütünlük | Kayıtlarda sha256 sakla, okurken doğrula; tutmuyorsa kaydı sil ve `null` dön |
| Süre sonu | Görselde `son_gosterim` + saklama günü; veride artık geçmeyen görsel anında atılır |
| Kota | Toplam boyut sınırı aşılırsa en eski kullanılanlar silinir |
| Ağ yoksa | Önbellekteki kopya gösterilir (çevrimdışı dayanıklılık) |
| Damga yokken | Damga okunamazsa önbellekteki kopya kullanılır (eski ama çalışır) |
