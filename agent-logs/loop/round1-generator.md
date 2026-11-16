Endpoint'i ekledim; `pytest` sonucu **43 passed**. Yalnızca `main.py` ve `test_main.py` değişti, commit atmadım. Testlerden sonra çalışma klasöründe `recipes.db` oluşmadı, yani gerçek veritabanına dokunulmadı.

## Değişiklikler

**`main.py`**
- **Veritabanı yolu:** `DB_PATH` artık `RECIPE_BOX_DB` ortam değişkeniyle değiştirilebiliyor. Bunu yaptım çünkü `init_db()` import sırasında çalışıyor ve testler başlamadan gerçek `recipes.db` dosyasını oluşturuyordu.
- **`scale_ingredient()`:** Satırın başındaki miktarı bulup factor ile çarpıyor. Üç biçimi tanıyor: tam veya ondalık sayı (`200`, `1.5`, `.5`), kesir (`1/2`) ve karışık sayı (`1 1/2`).
- **`_format_quantity()`:** Tam sayıları `2` diye, diğerlerini en fazla 2 ondalıkla ve sondaki sıfırlar olmadan yazıyor (`1.50` → `1.5`).
- **Endpoint:** `GET /recipes/{id}/scaled` önce mevcut `get_recipe()` fonksiyonunu çağırıyor, böylece bilinmeyen id'de 404 hatası aynı yerden geliyor. Factor sınırını FastAPI'nin `Query(gt=0, le=10, allow_inf_nan=False)` ayarı kontrol ediyor ve geçersiz değerde otomatik 422 dönüyor.

**`test_main.py`**
- Her test kendi boş veritabanıyla çalışıyor (`tmp_path` + `monkeypatch`).
- Her kural için test var: tam sayı, kesir, karışık sayı ve ondalık ölçeklemesi; sıfırların atılması; miktarsız malzemeler; 404; geçersiz factor (0, negatif, 10'dan büyük, `abc`, boş, `nan`, `inf`, hiç verilmemiş); tarifin hem API'de hem doğrudan SQLite'ta değişmediği.

`★ Insight ─────────────────────────────────────`
- **Hesaplar `Fraction` ile yapılıyor:** `1/3 × 3` tam olarak `1` çıkıyor; float kullansaydık `0.9999…` görebilirdik. Factor da `Fraction(str(factor))` ile çevriliyor, yoksa `0.1` tam 1/10 olmaz.
- **`(?![\d/.])` kontrolü:** Regex'in bir sayının ortasında durmasını engelliyor. Böylece `1.2.3` gibi bozuk bir girdi yanlış bir değere dönüşmek yerine olduğu gibi kalıyor.
- **Testteki env değişkeni:** `import main` satırından *önce* ayarlanıyor. Python modülü import ederken kodunu hemen çalıştırdığı için fixture tek başına yetmezdi.
`─────────────────────────────────────────────────`

## Aldığım kararlar
1. **Sonuç ondalık gösteriliyor, kesir değil.** "0.5 ise 0.5" kuralına uymak için `1/2 × 3` → `1.5` oluyor, `1 1/2` değil. Bunun bir bedeli var: `1/3` factor 1 ile `0.33` olarak dönüyor.
2. **Yuvarlama 2 ondalık.** Çok küçük sonuçlar `0`'a düşmesin diye 0.01'in altında 2 anlamlı basamağa geçiyor: `1 g × 0.001` → `0.001 g`.
3. **Sadece baştaki miktar ölçekleniyor.** `"2 eggs, beaten in 1 bowl"` → `"4 eggs, beaten in 1 bowl"`.
4. **Çözülemeyen miktar değişmeden bırakılıyor.** `"1/0 cup"` gibi bir değer hata vermiyor, olduğu gibi dönüyor.
5. **Response'a `factor` alanı ekledim.** Geri kalan alanlar normal tarifle aynı.
6. **Python 3.9 uyumluluğu.** Ortam 3.9 olduğu için `X | None` yerine `Optional` kullandım; ilk deneme bu yüzden import hatası verdi.

**Desteklenmeyenler:** `½` gibi Unicode kesirler, `1,5` gibi virgüllü ondalıklar ve `2-3 eggs` gibi aralıklar olduğu gibi kalıyor. İstersen regex'i bunları da kapsayacak şekilde genişletebilirim.
