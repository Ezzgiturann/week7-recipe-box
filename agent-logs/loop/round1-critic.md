Diff'i okudum. Testleri çalıştırmayı denedim ama `pytest` çağrısı onaylanmadı, bu yüzden bu değerlendirme tamamen koda bakılarak yapıldı. Aşağıdaki girdi→çıktı örnekleri regex ve kod üzerinden adım adım izlenerek çıkarıldı.

`★ Insight ─────────────────────────────────────`
- Hesap `Fraction` ile yapılıyor ve factor önce `str()`'e çevriliyor (`Fraction(str(0.1)) == 1/10`). Bu yüzden `1/3 × 3 = 1` tam çıkıyor, `0.99` olmuyor. İyi bir tasarım kararı.
- Regex'in sonundaki `(?![\d/.])` kontrolü yalnızca rakam, `/` ve `.` karakterlerine bakıyor. Sayının hemen ardından `-`, `,` ya da `½` gelirse sayıyı tam bir miktar sanıyor. Aşağıdaki hatanın kaynağı bu.
`─────────────────────────────────────────────────`

## 1. Correctness: **FAIL**

**Doğru çalışan kısımlar:**
- Factor doğrulaması doğru. `gt=0, le=10, allow_inf_nan=False` ile 0, negatif değerler, 10.01, `nan`, `inf`, `abc` ve boş değer 422 dönüyor.
- Tarif bulunamazsa 404 dönüyor (`get_recipe` hatayı yukarı iletiyor).
- `1/2 × 2 → 1`, `1 1/2 × 2 → 3`, `.5 × 3 → 1.5` doğru. `2.0 → 2` örneğindeki gibi gereksiz sıfırlar atılıyor.
- `"salt to taste"` ve `"1/0 cup"` olduğu gibi kalıyor.
- Orijinal veri değişmiyor. `json.loads` her istekte yeni bir liste üretiyor ve veritabanına hiçbir yazma yapılmıyor.

**Sorun:** Desteklenmeyen biçimdeki bazı girdiler değiştirilmeden bırakılmıyor, sessizce **yanlış** sonuç veriyor. Görev metni bu durumu açıkça soruyor ("Hatalı veya desteklenmeyen bir girdi yanlış sonuç oluşturuyor mu?"):

| Girdi | factor | Çıktı | Beklenen |
|---|---|---|---|
| `"1-2 cloves garlic"` | 2 | `"2-2 cloves garlic"` | `"2-4 ..."` ya da değişmeden kalması |
| `"1,5 kg un"` | 2 | `"2,5 kg un"` | `"3 kg un"` ya da değişmeden kalması |
| `"1½ cups"` | 2 | `"2½ cups"` | `"3 cups"` ya da değişmeden kalması |
| `"2x3 cm pieces"` | 2 | `"4x3 cm pieces"` | belirsiz |

Bunun nedeni `main.py:117`'deki `(?![\d/.])` kontrolünün `-`, `,` ve Unicode kesirleri dışlamaması. `"1,5"` örneği özellikle önemli, çünkü Türkçe tariflerde ondalık ayırıcı virgüldür. Kullanıcı bu girdiyle hiçbir hata almadan %40 eksik miktar görür.

**Küçük not (FAIL'in sebebi değil):** `_format_quantity` iki farklı hassasiyetle çalışıyor. `1 g × 0.005` sonucunu `0.01 g` olarak gösteriyor (%100 hata), ama `1 g × 0.004` sonucunu `0.004 g` olarak gösteriyor. Ayrıca `factor=1` verildiğinde bile metin değişiyor (`"1/3 cup"` → `"0.33 cup"`).

## 2. Tests: **FAIL**

**İyi taraflar:**
- Her test kendi geçici SQLite dosyasını kullanıyor (`tmp_path` + `monkeypatch`).
- Ortam değişkeni `main` import edilmeden önce ayarlanıyor, böylece gerçek `recipes.db` hiç oluşturulmuyor.
- Orijinal verinin hem API'den hem doğrudan SQL ile değişmediği kontrol ediliyor.
- Sınır değerler (0, 10, 10.01) ve tekrar eden ölçeklemenin birikmediği test ediliyor.
- Prompt'taki her kuralın en az bir testi var.

**Eksikler:** Hataların saklandığı girdiler hiç test edilmemiş. Bu testler olsaydı yukarıdaki hata yakalanırdı:
- `("1-2 cloves garlic", 2, ?)`: aralık biçimi
- `("1,5 kg un", 2, ?)`: virgüllü ondalık
- `("1½ cups", 2, ?)` ve `("½ cup", 2, "½ cup")`: Unicode kesirler
- `("1 g", 0.005, ?)`: yuvarlama sınırı (0.005 → 0.01)
- `("12 oz (340 g) pasta", 2, ...)`: yalnızca baştaki sayının ölçeklendiği bilinçli olarak belgelenmeli
- `("  2 g", 2, "  4 g")`: baştaki boşluğun (`lead` grubu) korunması test edilmemiş
- `("2 1/0 cup", 2, ...)`: tam sayı ile sıfır paydalı kesir bir arada test edilmemiş
- Dikkat: `pytest` sonucunu doğrulayamadım. Tamamlanma kriteri olan "pytest geçmeli" henüz kanıtlanmış değil.

## 3. Clarity: **PASS**

Kod okunaklı. Regex grupları adlandırılmış ve yorumlanmış. `_parse_quantity`, `_format_quantity` ve `scale_ingredient` net ve tek işe odaklanan fonksiyonlar. Hata durumları açık: geçersiz factor FastAPI doğrulamasıyla 422 dönüyor, geçersiz miktar bilinçli olarak değiştirilmeden bırakılıyor ("don't guess" yorumu). Küçük notlar:
- Testte `main.json.dumps` yerine `json` doğrudan import edilmeli.
- `tempfile.mkdtemp()` ile açılan dizin hiç silinmiyor.
- `_format_quantity`'deki iki aşamalı yuvarlama (`quantize` + `.2g` yedeği) bir docstring örneğiyle daha anlaşılır olur.

---

**Özet:** Correctness FAIL ve Tests FAIL. İkisinin kökü aynı: `-`, `,` ya da `½` gibi desteklenmeyen biçimler değiştirilmeden bırakılmak yerine sessizce yanlış ölçekleniyor ve bunları yakalayacak test yok. Clarity PASS. Kodu düzenlemedim. `pytest` çalıştırılamadığı için testlerin geçip geçmediği hâlâ belli değil.

VERDICT: REVISE
