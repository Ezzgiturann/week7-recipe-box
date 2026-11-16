Round 6'daki FAIL bulgusunu düzelttim ve istenen eksik testleri ekledim. İşe round 6 kodundan (commit `80b8886`) başladım. **`pytest`: 148 passed** (round 6'da 133'tü). Yalnızca `main.py` ve `test_main.py` değişti, `recipes.db` oluşmadı, commit atmadım.

## Correctness: başında olmayan miktarlar sessizce atlanıyordu → Düzeltildi

Hatanın nedeni, insan kararındaki genel kuralın yalnızca baştaki miktar *okunabildiğinde* uygulanmasıydı. Satır rakamla başlamıyorsa "miktarı yok" sayılıyor ve raporlanmıyordu.

- **Kuralı satırın tamamına genişlettim.** `_SECOND_NUMBER_RE`'nin adını `_ANY_NUMBER_RE` yaptım. Baştaki miktar okunamazsa satırın herhangi bir yerinde rakam ya da kesir aranıyor. Varsa satır `unscaled` listesine giriyor.
  - Bu satırlar artık raporlanıyor: `flour 200 g`, `Eggs: 2`, `a 400 g can tomatoes`, `about 2 cups`, `~2 cups`, `V8 juice`, `pinch of salt (½ tsp)`.
- **`_LOOKS_NUMERIC_RE`'yi kaldırdım.** Yeni kural onun yakaladığı her şeyi de yakalıyor (`1.2.3`, `-2 g` vb.). Raporun Clarity bölümündeki "iki regex benzer iş yapıyor" notu da böylece kapandı.
- **"Değişmeden döner, raporlanmaz" durumu artık tek bir şey demek:** satırda hiç rakam ya da kesir yok (`salt to taste`, `a pinch of nutmeg`). Docstring'i buna göre güncelledim ve kabul edilen sınırlamalara "miktar satırın başında değil" diye yeni bir kategori ekledim.

**Küçük gözlemler (FAIL sebebi değildi) → Belgelendi ve testle sabitlendi:**
- **Yazıyla yazılan sayılar:** `two eggs` ve `half a lemon` hâlâ ne ölçekleniyor ne de raporlanıyor. Asıl risk şu durumda: `2 cups plus one tbsp` girdisi `4 cups plus one tbsp` oluyor. Sadece rakam ölçekleniyor, `one tbsp` ise sessizce yanlış kalıyor. Bu sınırlamayı docstring'e yazdım. Kod değiştirmedim, çünkü bunu yakalamak bir kelime listesi gerektiriyor; bu da insan kararının vazgeçtiği kara liste yaklaşımına geri dönmek olurdu.
- **Factor 1'de yuvarlama:** `1/8 tsp` → `0.13 tsp`. Bu, round 4'te seçilen biçimlendirme kuralının sonucu. Docstring'e yazdım ve testle sabitledim.

## Tests (istenen eksik testlerin hepsi eklendi)
- **Başında olmayan miktarlar:** yukarıda listelenen 7 satır `unscaled` testine girdi.
- **Diğer Unicode kesirler:** `⅔` ×3 → `2`, `⅛` ×4 → `0.5`, `⅒` ×10 → `1`. Bunlar `limit_denominator(10)` yolunu test ediyor.
- **Belirsiz tire:** `2-3/4 cups` ×2 → `5.5 cups`. Tire, aralık değil karışık sayı olarak okunuyor (2¾). Bu karar docstring'de yazılı.
- **Factor 1'de yuvarlama:** `1/8 tsp` → `0.13 tsp`.
- **Yazıyla yazılan sayılar:** `test_number_words_are_a_documented_limitation` testi bu sınırlamayı bilinçli bir davranış olarak sabitliyor.

`★ Insight ─────────────────────────────────────`
- **Kural doğruydu, kapsamı eksikti:** İnsan kararındaki genel kural round 6'da yalnızca "baştaki miktardan *sonra*" uygulanıyordu. Bu turdaki düzeltme yeni bir kalıp eklemedi; aynı kuralı satırın tamamına genişletti. Sonuçta kod bir regex daha azaldı.
- **Sözleşme artık tek cümleyle anlatılabiliyor:** "Rakam yoksa dokunma; desteklenen baştaki miktar dışında bir rakam varsa raporla." İstemci boş bir `unscaled` listesini artık güvenle "her rakam doğru ölçeklendi" diye okuyabilir. Tek istisna yazıyla yazılan sayılar, o da belgelenmiş durumda.
`─────────────────────────────────────────────────`
