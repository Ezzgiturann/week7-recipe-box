Round 4'teki bulguların hepsini düzelttim. **`pytest`: 119 passed** (önceki turda 105'ti). Yalnızca `main.py` ve `test_main.py` değişti, `recipes.db` oluşmadı, commit atmadım.

## Correctness

**a) `70%` gibi yüzdeler ölçekleniyordu → Düzeltildi.**
- `_AMBIGUOUS_AFTER_RE` kuralına `\s*[%°]` ekledim. `70% dark chocolate`, `70 % ...`, `1.5% milk` ve `180°C oven` artık değişmeden kalıyor ve `unscaled` listesine giriyor.

**b) Çok uzun sayılarda 500 hatası → Düzeltildi.**
- Miktarı 100 basamakla sınırladım (`_MAX_QUANTITY_DIGITS`). Daha uzun miktarlar ayrıştırılmadan `unscaled` listesine giriyor.
- 100 sınırı gerçek tarif miktarlarının çok üstünde, Python'un 4300 basamak sınırının ise çok altında. Önceki turun 29 ve 41 basamaklı testleri hâlâ geçiyor.
- **Önemli bir not:** Bu ortam Python 3.9 ve 3.9'da 4300 basamak sınırı yok. Yani çökmeyi burada canlı olarak üretemedim. Ama yeni testler (5000 basamaklı tam sayı ve kesir) 3.11+ sürümlerinde de aynı şekilde geçer, çünkü bu satırlar `int()` ve `str()` çağrılarına hiç ulaşmıyor.

**c1) `-2 g` gibi negatif miktarlar işaretlenmiyordu → Düzeltildi.**
- `_LOOKS_NUMERIC_RE` artık başta `-`, `+` ya da `−` (Unicode eksi) işaretini de tanıyor: `-2 g`, `−2 g` ve `-.5 cup` işaretleniyor.
- Madde işaretli `- salt to taste` ise miktarsız sayılıyor ve listeye girmiyor.

**c2) `1 2 cups` gibi iki çıplak sayı → Düzeltildi.** Geçen tur bu noktaya katılmamıştım. Bu sefer iki kalıbı ayıran bir kural buldum:
- Bir sayıdan sonra boşlukla ayrılmış ikinci bir **çıplak sayı** geliyorsa satır belirsiz sayılıyor: `1 2 cups`, `2 400 g cans`.
- İkinci sayı **tireliyse** (`1 2-inch piece` → `2 2-inch piece`) bu bir adet + boyut kalıbı. Bu durum doğru ölçeklenmeye devam ediyor ve testle korunuyor.

**c3) factor=1 için özel davranış → Kaldırıldı.**
- Önceki iki turda bu davranışı savunmuştum. İnceleme bu sefer somut bir tutarsızlık gösterdi: factor=1 ile `1/3` aynen kalırken factor=1.0001 ile `0.33` oluyordu. Bu haklı bir tespit.
- Artık her factor aynı kuralları kullanıyor: `2.0 cups` → `2 cups`, `1/3` → `0.33`.
- **Bir bedeli var:** factor=1 ile çağrıldığında da kesirler ondalığa çevriliyor. Bu, "gereksiz sıfır olmasın" kuralının istisnasız uygulanmasının doğal sonucu.

## Tests (eksik olarak belirtilenlerin hepsi eklendi)
- **Yeni `unscaled` durumları:**
  - yüzde ve derece: `%`, `°`
  - negatif miktarlar: `-2`, `−2`, `-.5`
  - iki çıplak sayı: `1 2 cups`, `2 400 g cans`
  - 5000 basamaklı tam sayı ve kesir
- **factor=1 testleri:** `test_factor_one_uses_same_rules_as_any_factor` ve `test_format_does_not_jump_between_close_factors`.
- **Çok küçük factor (`test_tiny_factor_gives_exact_bounded_output`):** factor `1e-300` ile sonuç tam olarak `0.000…1` çıkıyor (299 sıfır), `0` ya da `1e-300` olmuyor. Çıktının uzunluğu en fazla 100 basamaklı miktar ve factor'ün basamak sayısı kadar oluyor.

## Clarity
- Docstring'deki bozuk satır kırılmasını düzelttim ve örnek listesini `70% cocoa` ve `-2 g` ile güncelledim.
- **"Yasak listesi" eleştirisine katılıyorum.** Bunu tamamen çözmenin yolu, yalnızca bilinen birimlerle (`g`, `cup`, `tbsp`…) başlayan satırları ölçekleyen bir izin listesi. Ama bu yöntem `3 eggs` ya da `2 onions` gibi birimsiz ve çok yaygın satırları ölçeklenmeyen satırlara çevirirdi. Bu, kapsamı ve davranışı ciddi şekilde değiştiren bir karar. İstersen bir sonraki adımda bunu ayrıca konuşabiliriz.

`★ Insight ─────────────────────────────────────`
- **Uzunluk sınırı en ucuz savunma:** `_MAX_QUANTITY_DIGITS` hem Python 3.11+'daki 4300 basamak sınırını hem de aşırı uzun Decimal hesaplarını tek kontrolle engelliyor. Kontrol ayrıştırmadan *önce* yapıldığı için riskli kod hiç çalışmıyor.
- **Testlerin güvencesi sürüme bağlı olabilir:** Bu testler 3.9'da çökme olmadan da geçerdi, yani 3.9'da yalnızca sınırın uygulandığını kanıtlıyorlar. Çökmeye karşı gerçek güvence, uzun girdinin `int()` çağrısına hiç ulaşmaması. Bunun sürümden bağımsız tek nedeni kontrolün ayrıştırmadan önce yapılması.
`─────────────────────────────────────────────────`
