Round 2'deki FAIL bulgularının hepsine katıldım ve hepsini düzelttim. Tek istisna factor=1 notu: orada mevcut davranışı bilerek korudum, nedeni aşağıda. **`pytest`: 90 passed.** Yalnızca `main.py` ve `test_main.py` değişti, `recipes.db` oluşmadı, commit atmadım.

**Response'ta bir değişiklik var:** artık `unscaled` adında yeni bir alan dönüyor. Satır başında miktar olup güvenle ölçeklenemeyen satırlar bu listede yer alıyor. Mevcut alanların hiçbiri değişmedi.

`★ Insight ─────────────────────────────────────`
- **Satırların üç durumu var.** `scale_ingredient` artık ölçeklenmiş satırı, değişmemiş satırı ya da `None` döndürüyor. `"salt to taste"` ile `"1,5 kg"` farklı şeyler: ilkinde ölçeklenecek miktar yok, ikincisinde var ama belirsiz. Önceki kod ikisini aynı şekilde ele alıyordu.
- **Format testleri JSON metnine bakmalı.** Python'da `2.0 == 2` doğru olduğu için eski test hatayı kaçırıyordu. Yeni test JSON metninde `'"factor":2,'` arıyor.
- **Unicode kesirler `unicodedata.numeric('⅓')` ile okunuyor.** Bu fonksiyon float döndürüyor (0.333…). `limit_denominator(10)` ile tam olarak 1/3'e çeviriyorum; tüm Unicode kesirlerin paydası 10 veya daha küçük.
`─────────────────────────────────────────────────`

## Correctness

**a) Desteklenmeyen satırlar sessizce dönüyordu → Düzeltildi.**
- **Unicode kesirler artık ölçekleniyor:** `½ cup` → `1 cup`, `1½` ve `1 ½` → `3`, `⅓ × 3` → `1`. Ayrı bir `_NUMBER` kalıbı ve `_parse_number` fonksiyonu ekledim.
- **Aralıklar artık iki sınırıyla birlikte ölçekleniyor:** `1-2` → `2-4`, `1 to 2` → `2 to 4`, `2 or 3` → `4 or 6`, `½-1` → `1-2`. Kullanılan ayırıcı (`-`, `–`, `to`, `or`) olduğu gibi korunuyor.
- **Gerçekten belirsiz olanlar `unscaled` listesinde:** Satırın metni değişmiyor ama listede görünüyor. Örnekler: `1,5`, `1,000`, `2x3`, `12 oz (340 g)`, `1/0`, `1-2-3`. `salt to taste` gibi miktarı olmayan satırlar bu listeye girmiyor, çünkü onlarda ölçeklenecek bir şey yok.

**b) `2-inch` yanlışlıkla ölçekleniyordu → Düzeltildi.**
- Sayıdan sonra tire ve harf geliyorsa (`2-inch`, `3-ounce`, `1-2-inch`) bu bir boyut, adet değil. Bu satırlar artık `unscaled` listesine giriyor.
- `1 2-inch piece` ise `2 2-inch piece` oluyor: yalnızca adet ölçekleniyor, boyut değişmiyor.

**c) Response'ta `"factor": 2.0` dönüyordu → Düzeltildi.**
- `_json_number` fonksiyonu tam sayı değerleri `int` olarak döndürüyor: `2.0` → `2`, `0.5` aynen kalıyor.

**d) factor=1 tutarsızlığı → Kısmen katılmıyorum, davranışı korudum.**
- "Sondaki sıfırları at" kuralı hesaplanmış değerler için. factor=1 olduğunda hiçbir hesap yapılmıyor. Bu durumda kullanıcının yazdığı metni değiştirmek (`1/3` → `0.33` gibi bilgi kaybettiren bir dönüşüm) beklenmedik olurdu.
- Bunu kodda açıkça belirttim: factor=1 kontrolü endpoint'te ve yorumuyla birlikte duruyor. Ayrıca `test_factor_one_is_identity` testiyle sabitlendi.

## Tests

1. **Factor testi hatayı gizliyordu → Düzeltildi.** `test_factor_is_echoed_without_trailing_zeros` artık response'un JSON metnini kontrol ediyor. `2`, `2.0`, `010`, `0.5` ve `1.25` girdilerini kapsıyor.
2. **Yanlış davranışı sabitleyen test → Düzeltildi.** `½ cup cream` artık "miktarsız" grubunda değil, değer testlerinde ve `1 cup cream` bekleniyor. Belirsiz satır testleri hem metnin değişmediğini hem de `unscaled` içinde olduğunu kontrol ediyor.
3. **Eksik edge case'ler → Hepsi eklendi.**
   - `2-inch` ve `3-ounce` (boyut ile adet ayrımı)
   - factor değerleri `1e-3` ve `0.0000001`. `str(float)` burada `'1e-07'` veriyor ve `Fraction` bunu doğru okuyor.
   - `"2.0"`, `"010"`, `0 g sugar`, `999999 g × 10`
   - Gerçek veritabanı kontrolü. `test_tests_do_not_use_real_db` önceden sadece yolları karşılaştırıyordu. Artık testler başlamadan `recipes.db` dosyasının durumunu (var mı, mtime ne) kaydediyor ve sonunda dosyanın oluşmadığını ya da değişmediğini doğruluyor.

## Clarity (küçük notlar)
- `get_recipe` route fonksiyonunu doğrudan çağırmak yerine `_fetch_recipe` adlı ortak bir yardımcı fonksiyon ekledim; iki endpoint de onu kullanıyor.
- "Geçersiz" ile "miktar yok" artık karışmıyor: `None` yalnızca geçersiz veya belirsiz miktar anlamına geliyor. Fonksiyonun docstring'i üç durumu da örnekle açıklıyor.
- Regex hizalamasını düzelttim ve tekrar eden ayırıcıyı `_RANGE_SEP` sabitine çıkardım.

**Hâlâ desteklenmeyenler:** `1,5` (virgüllü ondalık) ve `2 x 400 g` gibi satırlar ölçeklenmiyor, yalnızca `unscaled` listesinde gösteriliyor. Bunları metinden güvenilir şekilde ayırmak mümkün değil. Örneğin tarif dili bilinseydi `1,5` doğru okunabilirdi.
