Birleşik miktar hatasını insan kararındaki genel kuralla düzelttim ve testlerdeki tüm eksikleri ekledim. **`pytest`: 133 passed** (önceki turda 119'du). Yalnızca `main.py` ve `test_main.py` değişti, `recipes.db` oluşmadı, commit atmadım.

## Correctness: birleşik miktarlar sessizce yanlış ölçekleniyordu → Düzeltildi

- **Yeni kural (`_SECOND_NUMBER_RE`):** Baştaki miktar okunduktan sonra kalan metinde herhangi bir rakam ya da Unicode kesir varsa satır değişmeden kalıyor ve `unscaled` listesine giriyor. Desteklenen biçimlerin parçası olan sayılar zaten baştaki miktarın içinde okunduğu için bu kurala takılmıyor: aralığın ikinci sınırı, karışık sayının kesir kısmı gibi.
- **Kaldırılan kurallar:** Bu tek kural, önceki turlarda tek tek eklenen 8 kalıbın ve `_PAREN_QUANTITY_RE`'nin yerini aldı:
  - `,\d`
  - unicode kesir
  - üç parçalı aralık
  - `x\d`
  - `\d+/`
  - `e\d`
  - iki çıplak sayı
  - parantez içi miktar
- **Kalan küçük regex (`_NOT_AN_AMOUNT_RE`):** Yalnızca baştaki sayının *miktar olmadığı* iki durum için duruyor: `2-inch` ve `70%` / `180°C`. Bu satırlarda ikinci bir sayı olmadığı için genel kural onları yakalayamaz.
- **Docstring:** `scale_ingredient` docstring'i artık desteklenen biçimleri ve kabul edilen sınırlamaları kategorilere ayrılmış bir liste olarak gösteriyor.

**Kararın bedeli (bilinçli olarak kabul edildi):** Önceden doğru ölçeklenen iki satır artık `unscaled` listesine giriyor:
- `"2 eggs, beaten in 1 bowl"`
- `"1 2-inch piece ginger"`

Benzer şekilde, adında sayı geçen ürünler de bu listeye giriyor (`"2 cans V8 juice"`). Bunları testlerde "kabul edilen sınırlama" olarak işaretledim. Böylece ileride biri kuralı gevşetirse bu bilinçli bir karar olur.

## Tests (eksik olarak belirtilenlerin hepsi eklendi)
- **Birleşik miktarlar:**
  - `1 lb 4 oz beef`
  - `1 cup plus 2 tbsp flour`
  - `3 eggs or 4 egg whites`
  - `1/2 cup (120 ml) milk`
  - `½ cup plus ½ tbsp butter`
- **422 dönmesi gereken factor değerleri:** `-0`, `0.0`, `1/2`, `2x`.
- **Büyük harfli ayırıcılar:** `2 TO 3 eggs` → `4 TO 6 eggs`, `1 OR 2` → `2 OR 4`.
- **Yanlış alarm kontrolü:** `1 1/2-2 cups` → `3-4`. Aralığın ve karışık sayının kendi rakamları "ikinci sayı" sayılmıyor.
- **Sayısal olmayan id:** `/recipes/abc/scaled` → 422.
- **Gerçek veritabanı kontrolü:** Artık mtime'a ek olarak dosya içeriğinin SHA-256 hash'i de karşılaştırılıyor.

## Clarity
- Toplam regex sayısı azaldı ve belirsizlik kontrolü 10 alternatiften tek bir genel kurala ve iki alternatifli küçük bir regex'e indi. Yeni bir kenar durumu için artık listeye kalıp eklemek gerekmiyor; tanınmayan biçimler varsayılan olarak `unscaled` listesine düşüyor.

`★ Insight ─────────────────────────────────────`
- **"Tanımadığını raporla" yaklaşımı turları bitirir:** Beş tur boyunca her inceleme yeni bir kalıp buldu, çünkü kara listede her biçimin tek tek düşünülmesi gerekiyordu. Genel kural varsayılanı tersine çeviriyor: bilinmeyen biçim artık sessiz bir hata değil, görünür bir `unscaled` kaydı.
- **Bu bir kesinlik/kapsam ödünleşimi:** Kesinlik (yanlış sayı dönmemesi) arttı, kapsam (ölçeklenen satır oranı) biraz azaldı. Tarif ölçeklemede yanlış bir miktar, ölçeklenmemiş bir satırdan daha zararlı olduğu için bu doğru yön.
`─────────────────────────────────────────────────`
