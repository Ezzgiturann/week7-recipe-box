Round 7'deki FAIL bulgusunu ve küçük notu düzelttim, istenen eksik testlerin hepsini ekledim. **`pytest`: 182 passed** (round 7'de 148'di). Yalnızca `main.py` ve `test_main.py` değişti, `recipes.db` oluşmadı, commit atmadım.

**Başlangıç noktası:** Orkestratör notu "round 6 kodundan başla" diyordu, ama repo zaten round 7 commit'indeydi (`93c416d`, çalışma dizini temiz) ve critic de round 7 kodunu incelemişti. Notun önceki turdan kaldığını düşünüp round 7 kodundan devam ettim. Bu doğru değilse söyle, round 6'ya dönüp tekrar uygularım.

## Correctness

**Kelimeyle yazılan "miktar değil" ifadeleri sessizce ölçekleniyordu → Düzeltildi.**
- `_NOT_AN_AMOUNT_RE`'ye kelime biçimlerini ekledim: `percent`, `per cent`, `degree(s)`. `70 percent` ve `180 degrees` satırları artık `unscaled` listesine giriyor.
- **Tiresiz boyutlar:** Bir birim (`_SIZE_UNIT`) ve hemen ardından bir kap kelimesi (`_CONTAINER`) geliyorsa satır boyut sayılıyor: `2 inch piece`, `3 ounce can`, `1 lb bag`, `400 g tin`.
- **Yanlış alarm olmuyor:** Kap kelimesi yoksa birim miktarın kendisi oluyor ve satır ölçekleniyor (`3 ounces chocolate` → `6 ounces`). Birimsiz kap sayıları da ölçekleniyor (`2 large cans` → `4 large cans`).
- **Dürüst bir not:** `_CONTAINER` bir kelime listesi. Bu yüzden listede olmayan bir kap (`2 inch knob ginger` gibi) hâlâ kaçabilir.

**Sayı kelimeleri raporlanmıyordu → Düzeltildi.**
- `_NUMBER_WORD_RE`, rakamlar için kullanılan genel kuralın kelime karşılığı. Satırın herhangi bir yerinde `one`…`twelve`, `dozen`, `couple`, `half`, `quarter` ya da `third` geçiyorsa satır `unscaled` listesine giriyor: `two eggs`, `half a lemon`, `2 cups plus one tbsp`.
- Kelimeler `\b` ile tam kelime olarak aranıyor. Bu yüzden `bone-in`, `tender` ve `often` gibi kelimeler yanlış alarm vermiyor; bunlar testle sabitlendi.
- **Kabul edilen yan etki:** `1 cup half-and-half` (süt ürünü) ve `1 lemon, cut in half` da raporlanıyor. Yanlış ölçeklemek yerine raporlamak, insan kararındaki "emin değilsen raporla" yönüyle uyumlu. Docstring'e yazdım.

**Küçük not: `factor=10.0000000000000001` kabul ediliyordu → Düzeltildi.**
- `factor` artık `float` değil `Decimal`, bu yüzden sınırlar tam değer üzerinden kontrol ediliyor ve bu girdi 422 dönüyor. `Fraction(Decimal)` dönüşümü tam olduğu için `str()` hilesine de gerek kalmadı.
- `max_digits=400` eklememin nedeni şu: `1e-999999` pozitif bir değer, ama `Fraction`'a çevrilince devasa bir payda oluşturur. Bu sınırla 422 dönüyor, `1e-300` ise hâlâ geçiyor.

## Tests (istenen eksik testlerin hepsi eklendi)
- **Kelimeyle yazılan biçimler:** `70 percent`, `70 per cent`, `180 degree(s)`, `2 inch piece`, `3 ounce can`, `1 lb bag`, `400 g tin`, `3 cm pieces`.
- **Unicode rakamlar:** `٢ cups` ve `2٢ cups` artık raporlanıyor. Bunun için `_QUANTITY_RE`'ye `re.ASCII` ekledim: miktar olarak yalnızca 0-9 okunuyor, diğer yazı sistemlerinin rakamlarını genel kural yakalıyor.
- **`1-3/2 cups`:** Bileşik kesir kısmı paydasından büyük olduğu için "1 ile 3/2 arası mı, 2½ mı?" sorusu belirsiz. `_parse_number` artık bu tür karışık sayıları reddediyor ve satır raporlanıyor. `1-1/2` ise eskisi gibi `3` oluyor.
- **Factor hassasiyeti:**
  - `10.0000000000000001`, `1e-999999` ve `-inf` artık 422 dönüyor.
  - `test_factor_upper_bound_is_exact` sınırın tam olarak 10'da kesildiğini kontrol ediyor.
  - `test_high_precision_factor_is_exact` ile `10000000000000000 g × 1.0000000000000001` → `10000000000000001 g`. Float ile hesaplansaydı sonuç değişmezdi.
- **Sessiz yanlış sonucu sabitleyen test:** `test_number_words_are_a_documented_limitation` testini `test_number_words_are_reported` olarak yeniden yazdım. Artık doğru davranışı bekliyor.

`★ Insight ─────────────────────────────────────`
- **Aynı ilke, iki "alfabe":** Round 7 rakamlar için "okunan miktarın dışında sayı varsa raporla" kuralını getirmişti. Bu tur aynı kuralı kelimelere uyguladı. Açık kalan sorunların hepsi kelimeyle yazılmış sayılardı, çünkü kural yalnızca rakamlara bakıyordu.
- **Float ile Decimal farkı API sınırında başlıyor:** `float` tipindeki bir parametre, doğrulama yapılmadan *önce* yuvarlanıyor. Bu yüzden `le=10` kontrolü kullanıcının yazdığı değeri değil, yuvarlanmış `10.0`'ı görüyordu. Tam aritmetik ancak girdi baştan tam okunursa işe yarıyor.
- **Doğrulama aynı zamanda kaynak koruması:** `Decimal`'e geçince "pozitif ama devasa üslü" girdiler bir kaynak tüketme riski oldu. `max_digits` bu riski doğrulama katmanında, hesaplama başlamadan kapatıyor.
`─────────────────────────────────────────────────`
