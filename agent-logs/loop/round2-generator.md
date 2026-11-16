Raporun iki FAIL bulgusunu da doğru buldum ve düzelttim. Testleri bu sefer gerçekten çalıştırdım: **72 passed** (öncekinden 29 fazla). Yalnızca `main.py` ve `test_main.py` değişti, `recipes.db` oluşmadı, commit atmadım.

`★ Insight ─────────────────────────────────────`
- **Yanlış alarmları da test ettim.** `to\b` kuralı "1 to 2" ifadesini yakalıyor ama "2 tomatoes" ifadesini yakalamıyor. `\b` kelime sınırı demek ve "tomatoes" içinde "to"dan sonra sınır yok. `x` kuralı da yalnızca ardından rakam gelirse devreye giriyor, bu yüzden "2 xl eggs" normal ölçekleniyor.
- **Yeni yuvarlama tek bir formül:** `max(2, 1 - exact.adjusted())`. `adjusted()` en büyük basamağın üssünü veriyor (0.005 için -3). Böylece 1'den küçük değerlerde 2 anlamlı basamak, büyüklerde 2 ondalık korunuyor. Eski iki aşamalı yöntemdeki "0.004 doğru, 0.005 yanlış" tutarsızlığı kalmadı.
`─────────────────────────────────────────────────`

## Bulgular ve ne yaptığım

**1. Correctness FAIL: belirsiz girdiler yanlış ölçekleniyordu → Düzeltildi.**
- `main.py`'ye `_AMBIGUOUS_AFTER_RE` ve `_PAREN_QUANTITY_RE` ekledim. Baştaki sayıdan sonra şunlardan biri gelirse satır **olduğu gibi** dönüyor:
  - aralık: `-`, `–`, `—`, `~`, `to`, `or`
  - virgül ve ardından rakam
  - Unicode kesir (`½` gibi)
  - `x` veya `×` ve ardından rakam
  - parantez içinde ikinci bir miktar
- **Neden ölçeklemek yerine olduğu gibi bırakıyorum:** `1,5` Türkçede 1.5 demek, ama `1,000` bin demek ve ikisini metinden ayırmak mümkün değil. Yanlış tahmin 1000 kat hata verebilir. Bu, `1/0` için zaten uyguladığım "tahmin etme" ilkesiyle de tutarlı. Aralıkları (`1-2` → `2-4`) gerçekten ölçeklemek istersen sonraki adımda ekleyebilirim.
- **Bir bedeli var:** `2 x 400 g cans` da artık ölçeklenmiyor, oysa doğru sonuç `4 x 400 g` olurdu. Bu ifade `2x3 cm` ile aynı kalıba uyuyor ve ikisini ayırmanın güvenilir bir yolu yok.

**Küçük not 1: yuvarlama tutarsızlığı → Düzeltildi.**
- `1 g × 0.005` artık `0.005 g` veriyor, önceden `0.01` veriyordu. `0.995` sonucu `1` oluyor, `1.0` değil.

**Küçük not 2: factor=1 metni değiştiriyordu → Düzeltildi.**
- `factor == 1` artık metni hiç değiştirmiyor (`1/3 cup` aynen kalıyor). Bu yüzden `2.0` gibi sıfır atma testlerini factor 2 ile yeniden yazdım.

**2. Tests FAIL: eksik edge case'ler → Hepsi eklendi.**
- `test_ambiguous_quantities_unchanged` (15 durum): `1-2`, `1 - 2`, `1–2`, `1 to 2`, `2 or 3`, `1/2-1`, `1,5`, `1,000`, `1½`, `1 ½`, `2x3`, `2 x 400 g`, `2 × 400 g`, `12 oz (340 g)`, `2 1/2/3`.
- `test_ambiguity_check_has_no_false_positives`: `2 tomatoes`, `2 oranges`, `2 xl eggs`, `2 eggs, beaten` ve `1/2 cup milk (whole)` hâlâ doğru ölçekleniyor.
- `test_factor_one_is_identity`.
- Diğer eklenenler:
  - `½ cup cream` ve `2 1/0 cup` olduğu gibi kalıyor.
  - `"  2 g"` ifadesinde baştaki boşluk korunuyor.
  - Yuvarlama sınırları test ediliyor: 0.004, 0.005, 0.0123, 0.995.
- "pytest doğrulanmadı" notu: çalıştırdım, 72 passed.

**3. Clarity PASS: küçük notlar → Hepsi uygulandı.**
- `main.json.dumps` yerine `json` doğrudan import ediliyor.
- `mkdtemp()` dizini test bitince `atexit` + `shutil.rmtree` ile siliniyor.
- `_format_quantity` ve `scale_ingredient` için örnekli docstring yazdım. `scale_ingredient` docstring'i hangi satırların neden değişmediğini listeliyor.
