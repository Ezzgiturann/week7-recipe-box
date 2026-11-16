# Code Review: Task 3 (Ingredient scaling)

**Ne çalıştırdım:** `git diff main...HEAD` ile diff'i okudum ve `pytest` çalıştırdım: **90 passed**. Senaryoları canlı denemek için /tmp'ye yazma iznim yoktu. Aşağıdaki hatalı örnekleri `_QUANTITY_RE` ve `_AMBIGUOUS_AFTER_RE` regex'lerini adım adım izleyerek buldum, çalıştırarak doğrulamadım.

---

## 1. Correctness: **FAIL**

Görevdeki kuralların çoğu doğru uygulanmış:
- **Factor:** `0 < factor ≤ 10` sınırı var; `0`, negatif, `10.01`, `nan`, `inf` ve `abc` 422 dönüyor.
- **Kesirli ve ondalık miktarlar:** `1/2`, `1 1/2`, `½`, `1½`, `.5`, `1.0` destekleniyor.
- **Gösterim:** gereksiz sıfırlar atılıyor (`2.0` → `2`).
- **Diğer kurallar:** olmayan tarif 404 dönüyor, "salt to taste" gibi satırlar korunuyor ve veritabanına yazma yapılmıyor.
- **Kesin aritmetik:** hesaplar `Fraction` ile yapılıyor, bu yüzden `1/3 × 3` sonucu `1` çıkıyor, `0.99` değil.

Ama kodun kendi verdiği söz, yani desteklenmeyen biçimlerin "never scaled wrongly" olması, bazı yaygın girdilerde tutmuyor:

**a) Tireli mixed number yanlış sonuç veriyor.** ABD tariflerinde `1-1/2` yazımı çok yaygın.
```
"1-1/2 cups flour", factor=2  →  "2-1 cups flour"     (doğrusu: "3 cups flour")
unscaled = []                                          (hata raporlanmıyor)
```
Neden: `_NUMBER` içindeki mixed alternatifi (`\d+\s+\d+/\d+`) aradaki boşluğu zorunlu tutuyor. Bu yüzden `-` işareti `_RANGE_SEP` olarak eşleşiyor ve satır "1 ile 1/2 arası" bir aralık gibi okunuyor. Ölçeklenince bozuk bir miktar çıkıyor ve bu `unscaled` listesine de girmiyor.

**b) Unicode kesir çizgisi (U+2044 `⁄`) sessizce yanlış hesaplanıyor.**
```
"1 1⁄2 cups flour", factor=2  →  "2 1⁄2 cups flour"   (2.5 çıkıyor, doğrusu 3)
```
Neden: Yalnızca baştaki `1` sayı olarak eşleşiyor. `_AMBIGUOUS_AFTER_RE` içindeki `\s*\d+/` kontrolü sadece ASCII `/` karakterini tanıyor, bu yüzden satır işaretlenmiyor.

**c) Çok büyük miktarlarda 500 hatası oluşuyor** (benim çıkarımım, çalıştırarak denemedim):
```
"12345678901234567890123456789 g", factor=1.5  →  decimal.InvalidOperation → HTTP 500
```
Neden: `_format_quantity` sonucu varsayılan Decimal context'inde (28 basamak hassasiyet) `quantize` ediyor. Sonuç tam sayı değilse ve tam kısmı 27 basamak ya da daha uzunsa katsayı bu hassasiyeti aşıyor ve hata fırlatılıyor. Gerçek bir tarifte olası değil, ama "çok büyük değerler" sorusunun cevabı şu an "çöküyor".

Küçük bir not: `"2 3 eggs"` → `"4 3 eggs"` ve `"1e3 g"` → `"2e3 g"`. Bunlar zaten çöp girdi, ama ne doğru ölçekleniyor ne de işaretleniyor.

## 2. Tests: **PASS**

- Her kuralın testi var: 422 durumları (`0`, `-1`, `10.01`, `nan`, `inf`, `""`, eksik parametre), üst sınır olan `10`, 404, kesirli, ondalık, Unicode kesirler, miktarsız satırlar, aralıklar ve sıfır gösterimi. Factor'ün JSON'da `2.0` değil `2` olarak döndüğü de ham metin üzerinden kontrol ediliyor. Python'da `2.0 == 2` olduğu için bu iyi bir ayrıntı.
- Geçici veritabanı doğru kurulmuş: `main` import edilmeden önce `RECIPE_BOX_DB` env değişkeni ayarlanıyor, ayrıca her test için `tmp_path` ve `monkeypatch` kullanılıyor.
- Orijinal verinin değişmediği hem API'den hem doğrudan SQLite'tan kontrol ediliyor. Tekrarlanan ölçeklemenin birikmediği ve gerçek `recipes.db` dosyasına dokunulmadığı da test ediliyor.

Eksik testler (yukarıdaki hatalar tam da bu boşluklarda):
- `"1-1/2 cups flour"` ×2 için `"3 cups"` beklenmeli ya da satır `unscaled` listesine girmeli.
- `"1 1⁄2 cups"` (U+2044) aynı şekilde test edilmeli.
- Çok büyük ve tam sayı olmayan sonuç, örneğin 29 basamaklı bir miktar ×1.5. Şu an 404/422 dışında bir hata kodu dönmediğini doğrulayan bir test yok.
- `"1.2.3 cups"` ve `"1/2/3 cups"` için davranış belirsiz: değişmeden dönüyorlar ama `unscaled` listesine girmiyorlar. Bu hiç test edilmemiş.

## 3. Clarity: **PASS**

- İsimler net (`scale_ingredient`, `_format_quantity`, `_parse_number`, `unscaled`) ve docstring'ler örneklerle açıklanmış.
- `_fetch_recipe` çıkarılınca `get_recipe` ile yeni endpoint arasındaki kod tekrarı da gitmiş.
- `scale_ingredient` fonksiyonunun üç durumu (ölçeklenmiş metin / değişmemiş metin / `None`) docstring'de açıkça yazılmış.
- Hatalar açıkça ele alınıyor: belirsiz satırlar sessizce yutulmuyor, `unscaled` listesinde raporlanıyor.

Küçük bir tutarsızlık var: `_QUANTITY_RE` içindeki `(?![\d/.])` yorumu `"1.2.3"` girdisini "mid-token" olarak tanımlıyor. Bu satırlar değişmeden dönüyor ama `unscaled` listesine girmiyor. Docstring ise belirsiz miktarların raporlandığını söylüyor. Ayrıca `_AMBIGUOUS_AFTER_RE` oldukça yoğun bir regex. Satır satır yorumlanmış olsa da bakımı zor ve (a) ile (b)'deki hatalar da bu karmaşıklıktan çıkıyor.

`★ Insight ─────────────────────────────────────`
- **Neden 90 test geçtiği halde FAIL:** Testler geliştiricinin aklına gelen biçimleri doğruluyor. `1-1/2` gibi bölgesel yazımlar ancak gerçek tarif verisine bakınca ortaya çıkıyor.
- **Regex'te sıralama:** `_NUMBER` içinde alternatiflerin "en uzundan kısaya" dizilmesi doğru bir fikir. Ama aralık ayırıcısı olan `-` mixed number'ın bir parçası olabildiği için, sıralama tek başına "aralık mı, tek sayı mı" belirsizliğini çözemiyor.
- **Decimal hassasiyeti:** Python'da `quantize` için hassasiyet sınırı varsayılan context'ten (28 basamak) geliyor, sayının kendi büyüklüğünden değil. `Fraction` ile kesin hesap yapıp sonra `Decimal` ile biçimlendiren kodlarda bu sınırı unutmak kolay.
`─────────────────────────────────────────────────`

VERDICT: REVISE
