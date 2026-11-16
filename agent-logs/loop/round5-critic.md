# Code Review: Task 3, Ingredient Scaling (`git diff main...HEAD`)

`pytest -q` sonucu: **119 passed**. Kendi deneme komutlarımı (`python -c ...`) çalıştırma iznim reddedildi. Bu yüzden aşağıdaki hatalı örnekleri koddaki regex'leri adım adım takip ederek çıkardım, çalıştırarak doğrulamadım.

---

## 1. Correctness: **FAIL**

**Doğru çalışan kurallar:**
- **Factor sınırları:** `Query(..., gt=0, le=10, allow_inf_nan=False)` (`main.py:249`). `0`, `-1`, `10.01`, `nan`, `inf`, `abc`, boş değer ve eksik factor 422 dönüyor. `10` ve `1e-300` kabul ediliyor.
- **Kesirli factor değerleri:** `Fraction(str(factor))` sayesinde `0.1` tam olarak 1/10 sayılıyor, float hatası birikmiyor. `factor=1/2` yazımı 422 dönüyor. Bu, `float` tipiyle tutarlı ve kabul edilebilir bir karar.
- **Kesirli ve ondalık malzemeler:** `1/2`, `1 1/2`, `1-1/2`, `½`, `1½`, `.5` ve `0.750` doğru hesaplanıyor. Hesap `Fraction` ile yapıldığı için `1/3 × 3` sonucu `0.99` değil `1` çıkıyor.
- **Sondaki sıfırlar:** `2.0` → `2`, `0.5` → `0.5`. Factor değeri de response'ta `2` olarak dönüyor, `2.0` değil.
- **Diğer kurallar:** 404 dönüyor, miktarı olmayan malzemeler aynen korunuyor, veritabanına hiç yazılmıyor (sadece `SELECT` var, `_row_to_recipe` her seferinde yeni bir dict üretiyor).
- **Çok büyük ve çok küçük değerler:** Decimal hassasiyeti dinamik olarak ayarlandığı için 29 haneli ve 4300 hane sınırını aşan girdiler 500 hatası vermiyor.

**Hata: birleşik miktarlar sessizce yanlış hesaplanıyor.**

Kod sadece baştaki miktarı ölçekliyor. Aynı satırda ikinci bir miktar varsa onu ne ölçekliyor ne de `unscaled` listesine ekliyor:

| Girdi (factor=2) | Çıktı | Doğrusu | `unscaled` |
|---|---|---|---|
| `"1 lb 4 oz beef"` | `"2 lb 4 oz beef"` (2.25 lb) | 2 lb 8 oz (2.5 lb) | `[]` |
| `"1 cup plus 2 tbsp flour"` | `"2 cup plus 2 tbsp flour"` | 2 cup + 4 tbsp | `[]` |
| `"3 eggs or 4 egg whites"` | `"6 eggs or 4 egg whites"` | 6 or 8 | `[]` |

`"1 lb 4 oz"` satırının izlediği yol:
1. Kalan metin `" lb 4 oz beef"` oluyor.
2. `_AMBIGUOUS_AFTER_RE` (`main.py:145`) sadece kalan metnin **başına** bakıyor ve hiçbir seçenek eşleşmiyor. "İki çıplak sayı" kuralı da çalışmıyor, çünkü arada `lb` var.
3. `_PAREN_QUANTITY_RE` sadece parantez içine bakıyor.
4. Satır `main.py:238`'de yarı ölçeklenmiş halde dönüyor.

Bunun neden hata olduğu: kodun kendi ilkesi "desteklenmeyen format ya ölçeklenmez ya raporlanır, asla yanlış ölçeklenmez" (`test_main.py:271`). Bu ilkeyle `"12 oz (340 g) pasta"` tam da "ikinci miktar ölçeklenmeden kalır" gerekçesiyle `unscaled` listesine alınıyor. Aynı sorun parantez olmadan yazıldığında ise sessizce yanlış bir miktar dönüyor. `lb + oz` ve `cup plus tbsp` yazımları ABD tariflerinde çok yaygın. İnceleme sorusu "Hatalı veya desteklenmeyen bir girdi yanlış sonuç oluşturuyor mu?" ve bu örneklerde cevap evet.

Not: `"2 eggs, beaten in 1 bowl"` için sadece baştaki miktarın ölçeklenmesi bilinçli ve doğru bir karar (`main.py:127`). Sorun, ikinci sayının gerçekten bir miktar olduğu durumlardan bu ikisinin ayırt edilmemesi. Generator ya bu satırları raporlamalı ya da bunu kabul edilmiş bir sınırlama olarak açıkça belgelemeli.

---

## 2. Tests: **PASS**

**Güçlü yanlar:**
- **Geçici veritabanı doğru kurulmuş.** `main` import edilmeden önce `RECIPE_BOX_DB` geçici bir dizine yönlendiriliyor, çünkü `init_db()` import sırasında çalışıyor. Ayrıca her test `tmp_path` ile kendi boş veritabanını alıyor (`autouse` fixture).
- **Orijinal verinin değişmediği hem API hem SQLite seviyesinde kontrol ediliyor** (`test_scaling_does_not_modify_original`). Ölçeklemenin birikmediği de test edilmiş (`test_repeated_scaling_is_not_cumulative`). Gerçek `recipes.db` dosyasına dokunulmadığı mtime ile kontrol ediliyor.
- **Her kuralın testi var:** 422 durumları, 404, kesirler, ondalıklar, unicode kesirler, aralıklar, sondaki sıfırlar (JSON metninde `"factor":2,` kontrolü dahil), miktarsız malzemeler, sınır değerler (`10`, `10.01`, `0`, `1e-300`) ve çok büyük sayılar.

**Eksik testler (somut örnekler):**
- Birleşik miktarlar: `"1 lb 4 oz beef"`, `"1 cup plus 2 tbsp flour"`. Yukarıdaki hata tam da bu boşluktan kaçmış.
- `factor=1/2` ve `factor=-0` için 422 dönüldüğünü sabitleyen bir test.
- Büyük harfli aralık ayırıcı, örneğin `"2 TO 3 eggs"`. Kod `IGNORECASE` kullanıyor ama bu davranış test edilmemiş.
- Sayısal olmayan recipe id: `/recipes/abc/scaled` → 422.
- Gerçek veritabanı kontrolü sadece mtime'a bakıyor. `recipes.db` hiç yoksa bu test yalnızca "dosya oluşturulmadı" sonucunu kanıtlıyor. Bu yeterli, ama içerik hash'iyle karşılaştırmak daha sağlam olurdu.

---

## 3. Clarity: **PASS**

- İsimler açık: `scale_ingredient`, `_format_quantity`, `_parse_number`, `_fetch_recipe`. Ayrıca `get_recipe` ile ortak olan sorgu `_fetch_recipe`'ye taşınmış ve tekrar ortadan kalkmış.
- `scale_ingredient` üç durumlu bir sonuç dönüyor: ölçeklenmiş satır, değişmemiş satır veya `None`. Bu docstring'de örneklerle açıklanmış.
- Hatalar ortada: 422 ve 404 için FastAPI'nin standart mekanizması kullanılıyor, ölçeklenemeyen satırlar `unscaled` alanında raporlanıyor, 500'e yol açabilecek durumlar (4300 hane sınırı, Decimal hassasiyeti) yorumlarla anlatılmış.
- **Not (FAIL sebebi değil):** Beş generator turunun izleri belli. 9 regex var ve `_AMBIGUOUS_AFTER_RE` tek başına 10 seçenekli. Her seçeneğin yanında yorum olduğu için okunabiliyor, ama yeni bir edge case eklemek için listeye bir seçenek daha eklemek gerekiyor ve bu yapı giderek kırılganlaşıyor. Birleşik miktar hatası da bu "kara liste" yaklaşımının doğal sonucu: kod, tanıdığı riskli kalıpları yakalıyor, tanımadıklarını sessizce geçiriyor.

`★ Insight ─────────────────────────────────────`
- **Kara liste mi, beyaz liste mi:** `_AMBIGUOUS_AFTER_RE` riskli kalıpları tek tek sayıyor, listede olmayan her şeyi güvenli sayıyor. Bu yüzden her yeni edge case yeni bir generator turu demek. Diğer seçenek beyaz liste: "baştaki miktardan sonra ikinci bir sayı + birim varsa raporla" gibi tek ve genel bir kural, bilinmeyen kalıplarda varsayılan olarak raporlamaya düşer.
- **İyi bir tasarım kararı:** Factor'u `Fraction(str(float))` ile tam değere çevirmek, `0.1 × 3` sonucunun `0.30000000000000004` çıkmasını engelliyor. Biçimlendirmenin sadece en son adımda (`_format_quantity`) yapılması da "önce tam değerle hesapla, en son yuvarla" ilkesinin iyi bir örneği.
- **`unscaled` alanı:** İstenmemiş ama iyi bir ek. Sessiz hata yerine görünür bir sinyal veriyor. Bu inceleme de tam olarak bu sinyalin eksik kaldığı durumu buldu.
`─────────────────────────────────────────────────`

**Özet:** Correctness FAIL ("1 lb 4 oz" ve "1 cup plus 2 tbsp" gibi birleşik miktarlar sessizce yanlış ölçekleniyor ve raporlanmıyor). Tests PASS (eksik testler yukarıda). Clarity PASS.

VERDICT: REVISE
