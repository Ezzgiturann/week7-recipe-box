Bu turdaki üç Correctness hatasını ve testlerdeki eksikleri düzelttim. Bir küçük notta ise kodu bilerek değiştirmedim. **`pytest`: 105 passed** (önceki turda 90'dı). Yalnızca `main.py` ve `test_main.py` değişti, `recipes.db` oluşmadı, commit atmadım.

## Correctness

**a) `1-1/2` aralık gibi okunuyordu → Düzeltildi.**
- `_NUMBER` ve `_MIXED_RE` artık tam sayı ile kesir arasında tireyi de kabul ediyor. Tireli karışık sayı önce deneniyor: `1-1/2 cups` ×2 → `3 cups`.
- Ek bir güvenlik kontrolü daha ekledim: alt sınırı üst sınırdan küçük olmayan aralıklar (`2-1 cups`, `1 1/2-1 cups`) artık `unscaled` listesine giriyor. Benzer bir okuma hatası ileride çıkarsa da yanlış sayı üretilmez, işaretlenir.

**b) `⁄` (U+2044) yanlış hesaplanıyordu → Düzeltildi.**
- `_SLASH = "[/\u2044]"` sabitini ekledim. Kesir yazılan her yerde (sayı kalıbı, ayrıştırma ve belirsizlik kontrolleri) bu sabit kullanılıyor: `1 1⁄2` → `3`, `1⁄2` → `1`.

**c) Çok büyük miktarlarda 500 hatası → Düzeltildi.**
- Bulguyu kod üzerinden doğruladım: 29 basamaklı bir miktarı 2 ondalıkla `quantize` etmek 31 basamak hassasiyet istiyor, varsayılan sınır ise 28.
- `_format_quantity` artık `decimal.localcontext()` kullanıyor ve hassasiyeti sayının boyutuna göre ayarlıyor. Global ayar değişmiyor.

**Küçük not: `1.2.3`, `1/2/3` ve `1e3` → Düzeltildi.**
- Satır rakamla başlıyor ama okunamıyorsa artık "miktar yok" sayılmıyor, `unscaled` listesine giriyor (`_LOOKS_NUMERIC_RE`).
- `1e3` için `e[-+]?\d` kuralını ekledim.
- Böylece raporun Clarity bölümünde işaret ettiği, docstring ile davranış arasındaki tutarsızlık da kalmadı.

**Küçük not: `2 3 eggs` → Bilerek değiştirmedim.**
- Bir sayıdan sonra başka bir sayının gelmesi geçerli bir kalıp: `1 2-inch piece ginger` (1 adet 2 inçlik parça) ya da `2 400g cans`. Bunları işaretlemek, doğru ölçeklenen gerçek tarif satırlarını bozardı. `2 3 eggs` ise gerçek bir tarifte pek görülmeyecek bir girdi.

## Tests
- **Değer testleri:** `1-1/2`, `1⁄2`, `1 1⁄2`, `1-1⁄2`.
- **Aralık testleri:** `1 1/2-2` ve `1-1/2-2` → `3-4`.
- **Büyük sayı testi (`test_huge_amounts_do_not_crash`):** 29 basamak ×1.5, 41 basamak ×0.1 ve 41 basamaklı bir kesir.
- **`unscaled` testleri:** `1.2.3`, `1/2/3`, `1e3`, `1 1⁄2⁄3`, `2-1` ve `1 1/2-1`.

`★ Insight ─────────────────────────────────────`
- **Üç tur, aynı kök sorun:** Serbest metinden miktar okurken her yeni yazım biçimi yeni bir kenar durumu getiriyor. Bunu tamamen çözen asıl önlem `unscaled` listesi: ayrıştırıcının tanımadığı bir biçim artık yanlış bir sayıya dönüşmüyor, istemciye bildiriliyor.
- **`low < high` kontrolü:** "Bu sonuç mantıklı mı?" sorusunu soruyor. Belirli kalıpları tek tek yakalayan regex kurallarından daha geniş bir ağ sağlıyor, çünkü henüz düşünülmemiş okuma hatalarını da yakalayabiliyor.
`─────────────────────────────────────────────────`
