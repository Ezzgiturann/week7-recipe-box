Pytest geçiyor (182 passed). Doğrudan `scale_ingredient` çağıran deneme script'imin çalışması için onay verilmedi. Bu yüzden aşağıdaki iki hatalı örneği kodu satır satır izleyerek buldum, çalıştırarak doğrulamadım.

## 1. Correctness: FAIL

Prompt'taki açık kuralların hepsi karşılanıyor:
- **Factor sınırları:** Decimal ile `gt=0, le=10` kontrolü yapılıyor. 0, negatif değerler, `10.0000000000000001`, nan ve inf 422 dönüyor.
- **Kesir ve ondalık:** `1/2`, `1 1/2`, `1-1/2`, `½`, `.5` ve `0.750` doğru hesaplanıyor. Hesap `Fraction` ile tam yapılıyor.
- **Biçim:** Gereksiz sıfırlar atılıyor (2.0 yerine 2, 0.5 olarak 0.5).
- **404:** Bulunmayan tarifte dönüyor.
- **Veritabanı:** Hiç yazılmıyor, endpoint sadece okuma yapıyor.

Kabul kriterine göre FAIL sayılan şey, unscaled listesinde raporlanmadan dönen yanlış bir sayıdır. Bu tür iki durum buldum:

**a) Tireli yazılan boyut yakalanıyor ama tiresiz yazılan yakalanmıyor**
- Girdi: `"9 inch pie crust"`, factor=2
- Sonuç: `"18 inch pie crust"`, `unscaled: []`
- Neden: `_NOT_AN_AMOUNT_RE` tiresiz boyutu sadece arkasından `_CONTAINER` listesindeki bir kelime gelirse yakalıyor (`main.py:172`). "pie", "pan" ve "tortillas" bu listede yok. `"9-inch pie crust"` doğru şekilde raporlanıyor, aynı malzemenin tiresiz yazımı ise sessizce 18 inçlik tek bir kabuğa dönüşüyor.
- Aynı durum `"10 inch flour tortillas"` → `"20 inch flour tortillas"` için de geçerli. Docstring "2 inch piece" gibi tiresiz boyutların raporlandığını söylüyor.

**b) Sayı kelimesi listesi "twelve"de bitiyor**
- Girdi: `"twenty eggs"` veya `"fifteen almonds"`, factor=2
- Sonuç: satır aynen dönüyor ve `unscaled: []`
- Neden: `_NUMBER_WORD_RE` (`main.py:151-155`) sadece one…twelve, dozen, half, quarter ve third kelimelerini kapsıyor. Docstring (`main.py:238, 248`) "number words anywhere" raporlanır diyor. `"two eggs"` raporlanırken `"twenty eggs"` "miktarı olmayan malzeme" sayılıyor. Kullanıcı 2 kat tarifte "twenty eggs" görüyor ve bir uyarı almıyor.

Kabul kriterine göre FAIL sebebi olmayan, belgelenmiş sınırlamalar: `"1,5 kg"`, `"half-and-half"`, `"1/8 tsp"` sonucunun `"0.13"` olması ve `"2-3/4"` ifadesinin 2 ¾ olarak okunması.

## 2. Tests: PASS

- Prompt'taki her kural için test var:
  - factor sınırları ve geçersiz değerler: `test_invalid_factor_returns_422`, `test_factor_upper_bound_is_exact`
  - kesir, ondalık ve unicode miktarlar: `test_scaling_values`
  - miktarı olmayan malzemeler: `test_ingredients_without_quantity_unchanged_and_not_flagged`
  - gereksiz sıfırlar: `test_factor_is_echoed_without_trailing_zeros`
  - 404: `test_scaled_unknown_recipe_404`
- Uç değerler kapsanmış: 0, -0, 1e-300, 10, 10'u az geçen değerler, 5000 basamaklı sayılar ve ters aralıklar.
- Geçici veritabanı doğru kurulmuş: `main` import edilmeden önce `RECIPE_BOX_DB` ortam değişkeni ayarlanıyor ve her test için `tmp_path` kullanılıyor.
- `test_tests_do_not_use_real_db` gerçek `recipes.db` dosyasının mtime ve hash değerinin değişmediğini kontrol ediyor.
- Orijinal verinin değişmediği hem API'den hem de doğrudan SQL ile kontrol ediliyor (`test_scaling_does_not_modify_original`).

Eksik testler:
- `"9 inch pie crust"` ve `"10 inch flour tortillas"` (tiresiz boyut, container olmadan). Yukarıdaki 1a hatasını yakalardı.
- `"twenty eggs"` ve `"fifteen almonds"` (twelve'den büyük sayı kelimeleri). 1b hatasını yakalardı.
- Kesirli bir malzemenin 1'den küçük factor ile çarpılması, örneğin `"1/3 cup"` × 0.5 → `"0.17 cup"`. Şu anki testlerde kesirli malzemeler hep 1 veya daha büyük factor ile deneniyor.

## 3. Clarity: PASS

- İsimler anlaşılır: `_NOT_AN_AMOUNT_RE`, `_ANY_NUMBER_RE`, `_parse_number`, `_format_quantity`.
- Regex'ler ve kararlar yorumlarla açıklanmış.
- Hata yönetimi açık: `None` "güvenle ölçeklenemez" anlamına geliyor ve satır `unscaled` listesine ekleniyor.
- Küçük bir not: endpoint docstring'i (`main.py:303-305`) güncel değil. "`unscaled` lists ingredient lines that start with a quantity" diyor, ama bu round'dan sonra `"flour 200 g"`, `"two eggs"` ve `"V8 juice"` gibi baştan miktarla başlamayan satırlar da listeleniyor. Bu metin OpenAPI dokümanında da görünüyor. Bu tek başına FAIL için yeterli değil, ama düzeltilmesi iyi olur.

VERDICT: REVISE
