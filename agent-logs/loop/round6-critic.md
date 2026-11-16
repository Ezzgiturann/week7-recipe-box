## Code Review: Ingredient scaling (`task-c/scaling`)

Diff'i okudum ve `pytest` çalıştırdım: **133 passed**. Ek girdileri doğrudan denemek için bir script çalıştırmak istedim ama izin verilmedi. Bu yüzden aşağıdaki bulgular kod okumasına dayanıyor. Kodda hiçbir değişiklik yapmadım.

`★ Insight ─────────────────────────────────────`
- Uygulama üç durumlu bir sözleşme kullanıyor: ölçeklenmiş satır / hiç dokunulmamış satır / `None`, yani "unscaled" listesine gidecek satır. Asıl risk, bir satırın yanlışlıkla "miktarı yok" olarak sınıflandırılması. O satır hem değişmeden kalıyor hem de raporlanmıyor.
- Factor'ü `Fraction(str(factor))` ile tam kesire çevirmek iyi bir karar: `0.1` ikilik sistemdeki float değeri değil, tam olarak `1/10` oluyor. `1/3 × 3 = 1` gibi sonuçlar da `0.99` yerine tam çıkıyor.
`─────────────────────────────────────────────────`

### 1. Correctness: **FAIL**

**Düzgün çalışanlar:**
- Factor kontrolü doğru: `gt=0, le=10, allow_inf_nan=False`. `0`, `-0`, negatifler, `10.01`, `nan`, `inf`, `abc` ve boş değer 422 dönüyor.
- Ondalık değerler, kesirler, karışık sayılar (`1 1/2`, `1-1/2`), Unicode kesirler (`½`, `1½`) ve aralıklar (`1-2`, `1 to 2`) tam kesir aritmetiğiyle hesaplanıyor.
- Gereksiz sıfırlar atılıyor: `2.0 → 2`, `0.5 → 0.5`. Response'taki `factor` alanı da `2` olarak dönüyor, `2.0` değil.
- Tarif yoksa 404 dönüyor. Veritabanına sadece okuma yapılıyor; response yeni bir dict olarak üretiliyor.
- Başında sayı olan ama okunamayan satırlar (`1,5 kg`, `1 lb 4 oz`, `-2 g`, `70%`) docstring'de belgelenmiş ve `unscaled` listesinde raporlanıyor. Kabul kriterine göre bunlar FAIL sebebi değil.

**FAIL sebebi: başında olmayan miktarlar sessizce atlanıyor.**

`scale_ingredient` (`main.py`, `_QUANTITY_RE` ve `_LOOKS_NUMERIC_RE` kontrolü) iki regex'e de `^` ile bağlı. Satır rakamla başlamıyorsa "miktarı yok" sayılıyor ve hiç raporlanmadan geri dönüyor:

```
GET /recipes/{id}/scaled?factor=2   (ingredients: ["flour 200 g"])
→ "ingredients": ["flour 200 g"], "unscaled": []
```

Doğru sonuç `400 g` olmalıydı, ya da satır `unscaled` listesinde görünmeliydi. Aynı durum şu satırlarda da oluşuyor:
- `"Eggs: 2"`
- `"a 400 g can tomatoes"`
- `"about 2 cups stock"`
- `"~2 cups"`

Hepsi değişmeden dönüyor ve `unscaled: []` geliyor. İstemci boş listeyi "her şey doğru ölçeklendi" diye okuyor. Bu, kabul kriterindeki tanımın birebir karşılığı: unscaled listesinde raporlanmayan yanlış bir sayı.

Bu sınırlama belgelenmiş de değil. Docstring "miktarı olmayan" satırlara örnek olarak sadece `"salt to taste"`ı veriyor. Kod kendi içinde de tutarsız: `"2 cans V8 juice"` satırı, sonradan gelen bir rakam yüzünden raporlanıyor. `"flour 200 g"` satırındaki rakam ise hiç kontrol edilmiyor.

Karşı argüman: `docs/TASKS.md` "assume ingredients like '200 g flour'" diyor. Ama review sorusu, desteklenmeyen bir girdinin yanlış sonuç üretip üretmediğini soruyor. Bu girdi yanlış sonuç üretiyor ve bunu sessizce yapıyor.

**Daha küçük, FAIL sebebi olmayan gözlemler:**
- Sayı yerine kelime kullanılan satırlar da sessizce atlanıyor: `"two eggs"`, `"2 cups plus one tbsp"` → `"4 cups plus one tbsp"`. Prompt bunu istemiyor, ama belgelenmiş de değil.
- Factor 1'de bile sonuç yuvarlanıyor: `"1/8 tsp"` → `"0.13 tsp"`. Bu, belgelenmiş "en az 2 basamak" kuralının sonucu. Kabul edilebilir, ama ×1'de bile kesir bilgisi kayboluyor.

### 2. Tests: **PASS**

- Geçici veritabanı doğru kurulmuş. `RECIPE_BOX_DB` `import main`'den önce ayarlanıyor, çünkü `init_db()` import sırasında çalışıyor. Ayrıca her test kendi `tmp_path` DB'sini kullanıyor.
- Gerçek `recipes.db`'nin dokunulmadığı mtime ve hash ile kontrol ediliyor (`test_tests_do_not_use_real_db`).
- Orijinal verinin değişmediği hem API üzerinden hem SQL ile doğrudan kontrol ediliyor (`test_scaling_does_not_modify_original`). Tekrarlı çağrının birikmediği de test edilmiş.
- Prompt'taki her kuralın testi var: 422 sınırları, 404, kesirler, ondalıklar, miktarı olmayan satırlar, sondaki sıfırlar. Edge case'ler de geniş tutulmuş: `1e-300`, çok büyük sayılar, 4300 haneli string, Unicode eksi işareti, aralıklar.

Eksik testler (FAIL sebebi değil, ama eklenmeli):
- Başında olmayan miktarlar: `"flour 200 g"`, `"Eggs: 2"`. Böyle bir test olsaydı yukarıdaki hata yakalanırdı.
- Sadece `⅓` test edilmiş. `⅔`, `⅛` ve `⅒` yok; bunlar `limit_denominator(10)` yolunu kullanıyor.
- Belirsiz tire durumu: `"2-3/4 cups"` 2¾ mü, yoksa aralık mı? Sadece `1-1/2` test edilmiş.
- `"1/8 tsp"` gibi yuvarlanan bir kesrin factor 1'deki çıktısı.

### 3. Clarity: **PASS**

- `_fetch_recipe` ayrıştırması, 404 mantığının iki endpoint arasında tekrarlanmasını önlüyor.
- Regex'ler yoğun ama her biri yorumlanmış ve örneklenmiş (`_NUMBER`, `_NOT_AN_AMOUNT_RE`). Alternatiflerin sırasının neden önemli olduğu da açıklanmış ("longest forms first").
- `scale_ingredient`'in docstring'i dönüş sözleşmesini ve kabul edilen sınırlamaları açıkça listeliyor. İsimler anlaşılır: `exact_factor`, `_format_quantity`, `_json_number`.
- Hatalar bilinçli ele alınmış: Decimal hassasiyeti büyütülmüş, hane sayısına sınır konmuş, `1/0` için `None` dönüyor. Bunlar 500 hatası yerine kontrollü sonuç veriyor.
- Küçük not: `_LOOKS_NUMERIC_RE` ve `_SECOND_NUMBER_RE` benzer işler yapıyor. Correctness'taki hata da bu iki kontrolün sadece satır başında uygulanmasından kaynaklanıyor. Okunabilirlik açısından sorun değil.

### Özet

| Başlık | Sonuç | Ana sebep |
|---|---|---|
| Correctness | FAIL | `"flour 200 g"` ×2 → `"flour 200 g"` dönüyor, `unscaled: []` |
| Tests | PASS | Kapsamlı; başında olmayan miktarlar için test eksik |
| Clarity | PASS | İyi belgelenmiş; regex'ler yoğun ama yorumlu |

VERDICT: REVISE
