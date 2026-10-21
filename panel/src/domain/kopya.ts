/**
 * Derin kopya — `structuredClone` YERİNE kullanılır.
 *
 * Neden: panelde kopyalanan değerler Pinia/Vue **reactive Proxy**'leridir; `structuredClone`
 * bir Proxy'yi klonlayamaz ve `DataCloneError` atar ("could not be cloned"). Kaydetme başarılı
 * olsa bile ekranda "Beklenmeyen bir hata oluştu" uyarısı çıkıyordu.
 *
 * Kopyalanan veriler JSON belgeleri olduğu için JSON turu hem yeterli hem güvenli.
 */
export function kopya<T>(deger: T): T {
  if (deger === undefined || deger === null) return deger
  return JSON.parse(JSON.stringify(deger)) as T
}
