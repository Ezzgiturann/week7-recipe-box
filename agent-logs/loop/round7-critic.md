Diff'i ve iki dosyanın tamamını okudum. `pytest`'i çalıştıramadım çünkü komut izin isteminde reddedildi. Bu yüzden aşağıdaki sonuçlar kod okumaya dayanıyor, test sonucuna değil.

Bir not: `git diff main...HEAD` sadece round 7 değişikliğini gösteriyor (+46/−13 satır). Scaling özelliğinin geri kalanı diff'te görünmüyor, yani main'de zaten var gibi duruyor. Bu yüzden tüm özelliği dosyaların tam hâli üzerinden inceledim.

---

## 1. Correctness: **FAIL**

**Doğru çalışanlar:**
- **Factor doğrulaması:** `Query(gt=0, le=10, allow_inf_nan=False)` ile `0`, `-0`, negatif, `>10`, `nan`, `inf` ve `abc` değerleri 422 dönüyor.
- **Hesaplama:** `Fraction(str(factor))` ile hesap tam yapılıyor. Örneğin 0.1 tam olarak 1/10 sayılıyor.
- **Kesir, ondalık, karışık sayı ve aralık:** Hepsi doğru hesaplanıyor. `1/3 × 3` sonucu `1` çıkıyor, `0.99` değil.
- **Biçim:** Gereksiz sıfırlar atılıyor: `2.0` → `2`, `0.5` → `0.5`.
- **Diğer kurallar:** 404 doğru dönüyor ve veritabanına hiç yazma yapılmıyor.
- **Bilinen sınırlamalar:** `1,5 kg`, `1 lb 4 oz`, `2-inch`, `70%` gibi satırlar değiştirilmeden bırakılıyor, `unscaled`'da raporlanıyor ve docstring'de belgelenmiş. Kabul kriterine göre bunlar sorun değil.

**FAIL sebebi:** Bazı satırlarda sonuç sessizce yanlış çıkıyor. Yanlış sayı response'ta duruyor ama `unscaled`'da raporlanmıyor. Bu, kabul kriterinin açıkça FAIL saydığı durum.

| Girdi (factor=2) | Çıktı | `unscaled` | Sorun |
|---|---|---|---|
| `"70 percent dark chocolate"` | `"140 percent dark chocolate"` | `[]` | `"70% dark chocolate"` raporlanıyor, yazıyla "percent" ise ikiye katlanıyor. Kod kendi kuralıyla çelişiyor. |
| `"180 degrees oven"` | `"360 degrees oven"` | `[]` | `"180°C"` raporlanıyor, "degrees" yazımı raporlanmıyor. |
| `"2 inch piece ginger"` | `"4 inch piece ginger"` | `[]` | `"2-inch piece"` boyut olarak raporlanıyor. Tiresiz yazım ise boyutu sessizce ikiye katlıyor. |
| `"3 ounce can tuna"` | `"6 ounce can tuna"` | `[]` | `"3-ounce can"` için de aynı tutarsızlık var. |
| `"two eggs"`, `"half a lemon"` | Değişmiyor | `[]` | Satırda gerçek bir miktar var ama değişmeden dönüyor ve raporlanmıyor. |

Neden kabul edilmiş sınırlama sayılmıyor:
- İlk dört satırda `_NOT_AN_AMOUNT_RE` (`main.py:146-151`) sadece `-kelime` ve `%`/`°` biçimlerini yakalıyor. Aynı anlamın kelimeyle yazılmış hâli yakalanmıyor, ve sonuç yanlış bir sayı olup hiçbir yerde raporlanmıyor.
- Sayı kelimeleri (`main.py:226-227`) docstring'de belgelenmiş ama kabul kriteri hem belgelenmeyi hem `unscaled`'da raporlanmayı şart koşuyor. Docstring açıkça "*not* reported" diyor. Üstelik prompt'taki kural sadece miktarı olmayan satırları ("salt to taste") korumayı söylüyor, oysa "two eggs" satırında bir miktar var.

**Küçük not (tek başına FAIL sebebi değil):** `factor=10.0000000000000001` float'a çevrilince `10.0` oluyor ve 422 yerine kabul ediliyor. Pratikte etkisi yok.

## 2. Tests: **PASS**

- **Kurallar:** Her kuralın parametrik testi var: geçersiz factor için 422 (13 değer), 404, kesir, ondalık, Unicode kesir, miktarsız satır, sıfır atma (JSON metni üzerinden kontrol ediliyor) ve aralıklar.
- **Sınır değerler:** `0`, `-0`, `10`, `10.01`, `1e-300`, 5000 basamaklı sayı, 28 basamağı aşan Decimal ve boş malzeme listesi test edilmiş.
- **Geçici veritabanı:** `main` import edilmeden önce `RECIPE_BOX_DB` geçici bir dosyaya yönlendiriliyor. Her test de `tmp_path` ile kendi veritabanını alıyor.
- **Gerçek veritabanı:** `recipes.db` dosyasının değişmediği mtime ve hash ile kontrol ediliyor.
- **Orijinal veri:** Değişmediği hem API üzerinden hem doğrudan SQL ile kontrol ediliyor. Tekrarlı scaling'in birikmediği de test edilmiş.

**Eksik testler (somut):**
- `"70 percent ..."`, `"180 degrees ..."`, `"2 inch piece"`, `"3 ounce can"`: yukarıdaki hataları ortaya çıkaracak testler yok.
- `"1-3/2 cups"`: karışık sayı mı aralık mı olarak okunduğu test edilmemiş.
- `"٢ cups"` (Arapça-Hint rakamı): `\d` Unicode rakamlarla da eşleşiyor ama bu davranış test edilmemiş.
- `factor=10.0000000000000001`: float hassasiyetinin üst sınırı test edilmemiş.
- `test_number_words_are_a_documented_limitation` sessiz yanlış sonucu doğru davranış olarak sabitliyor. Correctness düzeltilince bu testin de değişmesi gerekecek.

## 3. Clarity: **PASS**

- **İsimlendirme:** İsimler açık: `_ANY_NUMBER_RE`, `_NOT_AN_AMOUNT_RE`, `_format_quantity`, `scale_ingredient`.
- **Diff:** Round 7, `_LOOKS_NUMERIC_RE` ile `_SECOND_NUMBER_RE`'yi tek bir `_ANY_NUMBER_RE` altında birleştirmiş. Tekrar azalmış ve kural sadeleşmiş: "okunan miktarın dışında kalan her rakam, satırı belirsiz yapar".
- **Hata yönetimi:** Okunabilir. `None` dönüşü "raporla" anlamına geliyor ve endpoint bunu tek yerde işliyor. Büyük sayılar için Decimal hassasiyeti ve 100 basamak sınırı, 500 hatalarını önlemek amacıyla gerekçesiyle belgelenmiş.
- **Küçük not:** `_NUMBER` regex'i yoğun ve `scale_ingredient` docstring'i uzun (~30 satır). Yine de örneklerle açıklandığı için anlaşılır.

`★ Insight ─────────────────────────────────────`
- Tasarım "emin değilsen raporla" prensibine dayanıyor ve iyi uygulanmış. Ama kara liste (`_NOT_AN_AMOUNT_RE`) sadece sembolleri (`-`, `%`, `°`) tanıyor. Aynı anlam kelimeyle yazılınca (percent, degrees, inch) liste işe yaramıyor.
- Round 7 rakamlar için "beyaz liste" mantığına geçmiş: okunan miktarın dışında rakam varsa satır raporlanıyor. Kelimeler için aynı mantık yok, bu yüzden açık kalan sorunların hepsi kelime tabanlı.
- `Fraction(str(factor))` ve Decimal `localcontext` ile tam aritmetik, kayan nokta hatalarını (`0.1 × 3 = 0.30000000000000004`) baştan engelliyor.
`─────────────────────────────────────────────────`

VERDICT: REVISE
