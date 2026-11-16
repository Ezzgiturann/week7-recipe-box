`GET /shopping-list?ids=1,2,3` artık çalışıyor ve pytest geçiyor (13 test: 3 eski, 10 yeni). Değişiklik sadece `main.py` ve `test_main.py`'de, mevcut endpoint'lere dokunmadım, commit atmadım.

**Aldığım kararlar:**

- **Tekrar tespiti:** Her malzemenin baştaki/sondaki boşluğunu siliyorum, sonra harf farkını yok sayarak karşılaştırıyorum (`casefold()` ile). Listeye ilk görülen yazılış giriyor: `"flour"` ve `"  Flour "` gelirse `"flour"` kalıyor. Boşluk silindikten sonra boş kalan malzemeyi listeye eklemiyorum.
- **Miktarlar:** Satırın tamamı karşılaştırılıyor. Bu yüzden `"200 g flour"` ile `"100 g flour"` ayrı kalıyor, `"200 G Flour"` ise `"200 g flour"`'un tekrarı sayılıyor.
- **Sıralama:** Sıra veritabanından değil, sorgudaki `ids` sırasından geliyor. Yani `ids=2,1` ile 2 numaralı tarifin malzemeleri önce geliyor. Tarifleri tek SQL sorgusuyla (`IN (?, ?, …)`) çekiyorum, değerler parametre olarak gidiyor, metin olarak sorguya eklenmiyor.
- **404:** Bulunamayan ID'lerin hepsi hata mesajında listeleniyor, sadece ilki değil.
- **422:** Boş `ids`, hiç `ids` gönderilmemesi, `1,abc`, `1,,2`, `-1` ve `1.5` hepsi 422 dönüyor. Kontrolü bilerek `isdigit()` yerine `[0-9]+` regex'iyle yaptım. `"²".isdigit()` `True` döner ama `int("²")` hata verir, bu da 422 yerine 500'e yol açardı. Sayıların etrafındaki boşluğa izin veriyorum (`1, 2` geçerli). Tekrarlanan ID'ler (`1,1`) hata vermiyor, sonuç zaten tekrarsız.

`★ Insight ─────────────────────────────────────`
- **Geçici veritabanı:** `get_db()` `DB_PATH`'i her çağrıda modülden okuyor. Bu sayede `monkeypatch.setattr(main, "DB_PATH", tmp_path / ...)` ile her test kendi boş SQLite dosyasını kullanıyor ve uygulama kodunu değiştirmek gerekmiyor. Yol fonksiyonun içinde sabit yazılmış olsaydı bu yöntem işe yaramazdı.
- **İki kademeli 422:** `ids` hiç gönderilmezse 422'yi FastAPI kendisi veriyor (`Query(...)` zorunlu parametre). Gönderilmiş ama bozuksa 422'yi `_parse_ids` veriyor.
`─────────────────────────────────────────────────`

**Bilmen gereken iki nokta:**

- `temp_db` fixture'ını sadece yeni testler kullanıyor. Eski 3 test hâlâ gerçek `recipes.db`'ye yazıyor, çünkü onları değiştirmemek için fixture'ı `autouse` yapmadım.
- `main.py` import edilirken `init_db()` çalıştığı için `recipes.db` dosyası her durumda oluşuyor. Bunu önlemek için `main.py`'nin import anındaki davranışını değiştirmek gerekirdi, o da kapsamın dışında kalıyordu.
