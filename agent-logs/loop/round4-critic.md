Testleri çalıştırma iznim yoktu (Bash ve geçici dosya yazma reddedildi), bu yüzden inceleme yalnızca diff'in ve `main.py`'nin okunmasına dayanıyor. Aşağıdaki girdi→çıktı örnekleri kodun elle izlenmesiyle bulundu, çalıştırılarak doğrulanmadı. `pytest`'in geçtiğini de doğrulayamadım.

`★ Insight ─────────────────────────────────────`
- Hesaplamalar `Fraction` ile kesin yapılıyor ve factor önce `str()` ile çevriliyor (`Fraction(str(0.1)) == 1/10`). Bu yüzden `1/3 × 3` sonucu `0.99` değil, tam olarak `1` çıkıyor.
- Kod satırları üçe ayırıyor: ölçeklenen, miktarı olmadığı için değişmeyen ve belirsiz olduğu için değişmeyip `unscaled` listesinde bildirilen. "Yanlış sonuç verme, bildir" yaklaşımı doğru. Ama bu güvence sadece regex'in tanıdığı belirsiz kalıplar için geçerli.
`─────────────────────────────────────────────────`

## 1. Correctness — FAIL

Ana kurallar karşılanmış:
- Factor sınırı (`gt=0, le=10, allow_inf_nan=False`) doğru.
- 404 için `_fetch_recipe` kullanılıyor.
- Kesirli, ondalık ve unicode miktarlar doğru hesaplanıyor.
- Miktarı olmayan satırlar korunuyor.
- Gereksiz ondalık sıfırlar siliniyor.
- Veritabanına yazılan bir şey yok.

Ancak hatalı veya desteklenmeyen girdiler hâlâ yanlış sonuç ya da çökme üretiyor:

**a) Yüzdeler sessizce ölçekleniyor (`main.py:217-221`).** `"70% dark chocolate"` girdisi factor=2 ile `"140% dark chocolate"` oluyor ve `unscaled` listesine de girmiyor. `_AMBIGUOUS_AFTER_RE` `%` karakterini kapsamıyor. Gerçek tariflerde sık görülen bir girdi ve sonuç fiziksel olarak anlamsız. Bu, kodun kendi "asla yanlış ölçekleme yapma" ilkesine aykırı.

**b) Çok uzun sayılar HTTP 500 veriyor (`main.py:180`, `main.py:192`).** `RecipeIn` uzunluk sınırı koymadığı için 5000 basamaklı bir miktar (`"111…1 g"`) kaydedilebiliyor. Python 3.11+ `int`/`str` dönüşümünü 4300 basamakla sınırlıyor. Bu yüzden `Fraction(text)` ve `str(value.numerator)` `ValueError` fırlatıyor ve bu hata yakalanmıyor. `test_huge_amounts_do_not_crash` sadece 41 basamağa kadar test ediyor. "Büyük değerde çökmez" iddiası bu sınırda bozuluyor.

**c) Diğer sessiz tutarsızlıklar (düşük önem):**
- `"-2 g sugar"` olduğu gibi kalıyor ama `unscaled` listesinde bildirilmiyor. `_LOOKS_NUMERIC_RE` `-` ile başlayan satırı tanımıyor.
- `"1 2 cups flour"` factor=2 ile `"2 2 cups flour"` oluyor. İkinci sayı belirsiz sayılmıyor.
- factor=1 durumunda `"2.0 cups rice"` aynen dönüyor. Bu, "gereksiz ondalık sıfır olmasın" kuralıyla çelişiyor. Ayrıca factor 1'de `"1/3"` kesir olarak kalırken 1.0001'de `"0.33"` oluyor, yani çıktı formatı factor'e göre değişiyor.

## 2. Tests — PASS

- Her kural için test var: factor sınırları, `nan`/`inf`/boş/eksik factor, 404, kesir, ondalık, unicode, karışık sayılar, aralıklar, sıfır temizleme ve miktarsız satırlar.
- Geçici veritabanı doğru kurulmuş. `RECIPE_BOX_DB`, `main` import edilmeden önce ayarlanıyor ve her test için `tmp_path` + `monkeypatch` kullanılıyor.
- Orijinal verinin değişmediği hem API'den hem doğrudan SQLite'tan kontrol ediliyor (`test_scaling_does_not_modify_original`).
- Gerçek `recipes.db` dosyasının değişmediği mtime ile kontrol ediliyor.
- Aynı tarifi tekrar ölçeklemenin birikmediği test edilmiş.
- Belirsiz kalıplar ve yanlış alarm vermeme durumları ayrı ayrı test edilmiş.

Eksik testler. Bunlar 1. başlıktaki sorunları yakalardı:
- `"70% dark chocolate"` → satır değişmemeli ve `unscaled` listesinde olmalı.
- `"1" * 5000 + " g"` → 500 değil, 200 dönmeli ve satır `unscaled` listesinde olmalı.
- `"-2 g sugar"` → `unscaled` listesinde bildirilmeli.
- `"1 2 cups flour"` → belirsiz sayılmalı.
- Çok küçük factor (`1e-300`) ile çıktının ne kadar uzadığı test edilmemiş.

## 3. Clarity — PASS

- İsimler açık: `_parse_number`, `_format_quantity`, `scale_ingredient`, `_fetch_recipe`.
- Regex sabitleri parçalara bölünmüş ve her alternatifin yanında örnek yorum var.
- Mevcut `get_recipe` mantığı `_fetch_recipe`'ye taşınarak tekrar önlenmiş.
- Küçük notlar:
  - `scale_ingredient`'ın `None` döndürüp "flag'le" anlamı taşıması alışılmadık, ama docstring'de açıkça yazıyor.
  - Aynı docstring'de `"2-1 cups"). The caller` satır kırılması bozuk.
  - `_AMBIGUOUS_AFTER_RE` yoğun bir regex. Sorun (a)'nın gösterdiği gibi, bu bir izin listesi değil bir yasak listesi ve kapsam dışı kalan kalıplar (`%` gibi) kolayca gözden kaçıyor.

VERDICT: REVISE
