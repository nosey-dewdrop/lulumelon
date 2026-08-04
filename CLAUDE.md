# lulumelon

Bir markanın dil modellerinde ne kadar göründüğünü ölçer, ve ölçtüğü sayının
yanına o sayının ne kadarının gerçek olduğunu koyar. Klasör adı `youkiddingme`,
marka `lulumelon`.

**Bu repo PUBLIC.** Buraya iş bilgisi, müşteri adı, takvim, anahtar parmak izi
ya da kişisel not yazılmaz. Oturum devri notları repo dışında,
`~/damla_projects_2026/reports/` altında tutulur.

## durum

934 pytest yeşil, 45 node testi yeşil. Süit ağ kapalı çalışır, anahtar harcamaz.

    python3 -m pytest lulumelon/tests
    npm test

## mimari, ve neden böyle

Duvar ürünün kendisi. `mirror/` saf aritmetiktir, ağa hiç dokunmaz ve
`collect/`'ten import etmez. `collect/` ağa dokunan tek yerdir ve hiçbir şey
hesaplamaz. Bir sayının dosyadan yeniden üretilebilmesinin sebebi bu ayrım.

- `mirror/` — intervals, variance, ablation, lift, compare, report, sources, stability, types, screen, names
- `collect/` — ask, ledger, session, budget, detect, subject, audit, harvest, propose, replica, replay
- `cli.py` — setup, init, doctor, collect, draft, usage, ablate, lift, report, rivals, verify, plan, size

## kalıcı kararlar

- **Ölçüm kapısı rakibi sayar, müşteriyi asla.** Müşterinin kendi anılma oranına
  göre eleme yapmak, iyi puan aldığı soruları tutup kötü aldıklarını atmak
  demektir, yani yayınlanan sayıyı aleyhindeki kanıtı silerek yükseltmek. Rakip
  beyan edilmemişse ücretli tur koşulmaz. Bu bir eksiklik değil, karardır.
- **Üçüncü hüküm geçiş sayılmaz.** Aralık tabanı sarıyorsa `undecided`, ve bu
  geçmiş değildir. Kanıtın en ince olduğu yerde açılan kapı hiç kapanmamıştır.
- **Çekiliş sayısı tabandan türetilir, sabit değil.** 0.3→2, 0.5→4, 0.6→6, 0.75→12.
- **Token masrafını müşteri öder.** Kotayı sağlayıcının ödemesi rakipleri k=1'e
  mahkum ediyor, ve k=1'de model gürültüsü ile sorudan soruya değişim
  cebirsel olarak ayrışmıyor.
- **Hiçbir şey yeniden denenmez, hiçbir şey düşürülmez.** Başarısız istek
  `status="error"` ile deftere yazılır. Başarıya kadar tekrar etmek bir filtredir.
- **Temizleme hattında sıra bir güvenlik kararıdır.** Anahtar deseni kart ve
  telefon desenlerinden önce koşar, çünkü bir anahtarın kuyruğu geçerli bir kart
  numarası olabilir ve geniş desen önce koşarsa diskte anahtarın öneki ve
  sağlayıcısı kalır. Yarısı silinmiş bir sır silinmemiş sayılır.

## çalışma kuralları

- Bir adım bir commit, bitince push. Mesaj lowercase İngilizce, co-author asla.
- Yeni testi mutasyonla doğrula, ve mutasyon turunu `PYTHONDONTWRITEBYTECODE=1`
  ile koş. Kaynağı `cp` ile geri yüklerken kaynak ve `.pyc` aynı saniyeye
  düşerse Python bayat bytecode'u taze sayar ve test sonucu yalan olur.
- Kırmızı testle commit atma. Zinciri kurarken testin kendi çıkış kodunu kontrol et.
- Davranışı varsayma, kodu oku. Testi koda uydur, kodu testine değil.
- Sahte veri, TODO, iskele alanı, ölü kod bırakılmaz.
- README'nin kendi kapısı var: her modül layout'ta geçmeli, her komut README'de
  görünmeli, test sayıları güncel olmalı.
- Em dash yasak, her yüzeyde. Testi var (`test_typography.py`).

## açık borç

- `lulumelon/demo.py` çalışmıyor, relative import hatası.
- README'de kurulum talimatı yok.
- `/ledger/` sadece repo kökünde gitignore'da; alt dizinlerdeki ledger korumasız
  ve `ensure_gitignored` ledger'ı hiç eklemiyor.
- `.env` anahtarı diske 0644 ile düşüyor, 0600 sonradan veriliyor (`keys.py:444`).
  Doğrusu `os.open(..., O_CREAT|O_EXCL, 0o600)`.
- `pyproject.toml` setuptools>=68 diyor ama `license = "MIT"` setuptools 77
  istiyor; 68, 70 ve 76 ile build çöküyor. `pytest>=8` tabanı da yanlış,
  8.0.0'da 22 hata veriyor, 8.1'de temiz.
- LICENSE dosyası yok ama metadata MIT diyor.
- Sağlayıcı varsayılanları komutlar arası ayrışıyor: init, doctor ve plan
  perplexity; collect ve draft anthropic. `docs/keys.md` baştan sona Perplexity
  anlatıyor.
- Bu build sadece iki motor çağırabiliyor, perplexity ve anthropic.
- Ölçülüp elenen sorunun METNİ kayboluyor. Taslak defteri `p7 barren` yazıyor,
  kayıtlar promptun id'sini taşıyor ve sözlerini taşımıyor, konu dosyasına da
  sadece geçen soru giriyor. 4 Ağustos'ta 20 sorudan 19'unun metni bu yüzden
  hiçbir yerde kalmadı. "Ölen hiçbir şey kaybolmaz" kuralı bedava kapılarda
  tutuyor, ücretli ölçümde tutmuyor.
- `lulu rivals` bir turun adlarını sayar ama isimleri hâlâ elle `--rivals`'a
  geçiriliyor; iki ucu birleştiren adım yazılmadı. Sayım, bir turda hiç cümle
  içinde geçmeyen ve imlasında iz taşımayan adı düşürür (`Twelve Data`).
