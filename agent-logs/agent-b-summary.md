Tag filtresi hazır ve `pytest` geçiyor (10/10: 3 eski, 7 yeni test). Sadece `main.py` ve `test_main.py` değişti, commit atmadım.

**Aldığım kararlar**

- **Parametre tipi:** `tag`, `Optional[list[str]] = Query(default=None)` olarak tanımlı. FastAPI tekrar eden `?tag=a&tag=b` değerlerini kendisi listeye çeviriyor. Parametre hiç verilmezse `None` geliyor ve tüm tarifler eskisi gibi dönüyor. Projedeki Python 3.9.6 olduğu için `list[str] | None` yerine `Optional` kullandım; ilk denemede o sözdizimi hata verdi.
- **Filtreyi Python'da yaptım, SQL'de değil:** Etiketler veritabanında JSON metni olarak duruyor. SQLite'ın `json_each` ve `lower()` fonksiyonlarıyla da yapılabilirdi, ama `lower()` sadece ASCII harfleri küçültüyor. Python'un `casefold()`'u Türkçe karakterler dahil Unicode'u da doğru eşleştiriyor. Bu ölçekte tabloyu baştan sona okumak sorun değil.
- **Eşleşme:** Hem sorgudaki hem tarifteki etiketler `strip().casefold()` ile normalize ediliyor. "Herhangi biri" (VEYA) kuralı için sorgudaki etiketleri bir kümeye koyup `any(...)` ile kontrol ediyorum.
- **422 kontrolü:** `Query(min_length=1)` listedeki her elemana değil listenin kendisine uygulandığı için işe yaramıyor. Bu yüzden kontrolü elle yazıp `HTTPException(422)` döndürdüm. Boş değer geçerli etiketlerle birlikte gelse de (`?tag=breakfast&tag=`) 422 dönüyor.
  - **Senin onaylaman gereken bir yorum:** Sadece boşluktan oluşan etiketleri (`?tag=%20`) de boş sayıp 422 döndürüyorum. Kuralı tam olarak `""` diye düşündüysen `strip()`'i kaldırmak yeterli.
- **Sıralama:** Sonuçlar mevcut `ORDER BY id` sırasını koruyor. Testler de bu yüzden listeyi tam sırasıyla kontrol edebiliyor.

**Geçici veritabanı**

`get_db()`, `DB_PATH` değişkenini her çağrıldığında yeniden okuyor. Bu sayede `temp_db` fixture'ı `monkeypatch` ile `main.DB_PATH`'i pytest'in `tmp_path` klasörüne yönlendirip `init_db()` çağırıyor ve test için örnek tarifleri ekliyor. Her test boş bir veritabanıyla başlıyor ve test bitince `monkeypatch` eski yolu geri koyuyor.

**Bilmen gereken iki sınırlama**

- Eski 3 test hâlâ gerçek `recipes.db`'ye yazıyor. Kapsam gereği onlara dokunmadım. İstersen fixture'ı `autouse=True` yapıp onları da geçici veritabanına alabiliriz.
- `main.py` import edildiği anda `init_db()` çalıştığı için `recipes.db` dosyası yine oluşuyor. Testler yalnızca bu import sırasında dosyayı açıyor, içine bir şey yazmıyor.

`★ Insight ─────────────────────────────────────`
- `DB_PATH` modül seviyesinde import anında sabitlenmiş olsaydı (örneğin `connect(DB_PATH)` doğrudan import sırasında çağrılsaydı), `monkeypatch` hiçbir şeyi değiştirmezdi. Yöntemin çalışması, yolun her çağrıda yeniden okunmasına bağlı.
- `?tag=` gönderildiğinde FastAPI `[""]` üretir, yani parametre "verilmiş ama boş" olur. `None` ise "hiç verilmemiş" demek. Bu ayrım sayesinde "parametre yoksa her şeyi döndür" ile "boş parametreye 422 ver" kuralları birbirine karışmadan yaşayabiliyor.
`─────────────────────────────────────────────────`
