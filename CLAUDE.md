# lulumelon

Bir markanın dil modellerinde ne kadar göründüğünü ölçer, ve ölçtüğü sayının
yanına o sayının ne kadarının gerçek olduğunu koyar. Klasör adı `youkiddingme`,
marka `lulumelon`.

**Bu repo PUBLIC.** Buraya iş bilgisi, müşteri adı, takvim, anahtar parmak izi
ya da kişisel not yazılmaz. Oturum devri notları repo dışında,
`~/damla_projects_2026/reports/` altında tutulur.

## durum

986 pytest yeşil, 45 node testi yeşil. Süit ağ kapalı çalışır, anahtar harcamaz.

    python3 -m pytest lulumelon/tests
    npm test

## mimari, ve neden böyle

Duvar ürünün kendisi. `mirror/` saf aritmetiktir, ağa hiç dokunmaz ve
`collect/`'ten import etmez. `collect/` ağa dokunan tek yerdir ve hiçbir şey
hesaplamaz. Bir sayının dosyadan yeniden üretilebilmesinin sebebi bu ayrım.

- `mirror/` — intervals, variance, ablation, lift, compare, report, sources, stability, types, screen, names
- `collect/` — ask, ledger, session, budget, detect, subject, audit, harvest, propose, replica, replay
- `cli.py` — setup, init, doctor, collect, draft, usage, ablate, lift, report, rivals, screened, publish, verify, plan, size

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

## site kanunu (src/, landing page)

- **Soru soran her başlık "?" ile biter.** İsim öbeği başlık ("what it measures")
  kaçamaktır; başlık soruyu ima ediyorsa açık soruya çevrilir ("what does it
  measure?"). Damla'nın ana kuralı, her yüzeyde geçerli.
- Renk dünyası pembe ve lila, ve ikisi de terminalin kendi paletinden gelir
  (`--lilac`, `--pink`). Dışarıdan palet getirilmez, gradient yoktur, köşe
  yarıçapı 3px'i geçmez, dinlenme halinde gölge yoktur.
- Terminal sayfanın EN ÜSTÜNDE durur, başlıktan da wordmark'tan da önce.
  Ziyaretçi tek kelime okumadan koşuyor olmalı; marka adını terminalin kendi
  ilk satırı söylüyor. Ürünün iddiası bir cümle değil, olan bir şey.
- Tipografi: gövde 14.5px, ikincil 13px, kart başlığı 1.15rem, h1 2.1rem.
  5 Ağu'da iki uçtan da geçildi, Damla önce "eşek kadar" dedi sonra "çok küçük";
  bu satır o iki reddin arasında kalan ölçü.
- Emoji Damla'nın paletidir ve sabittir: 💞🎀✨💘🍉💫. Kırmızı kalp ASLA.
  Palet SAYFAYA DAĞILIR, bir yere DÖKÜLMEZ: altısını yan yana tek satıra
  koymak "lök" diye reddedildi (5 Ağu). Yeri kağıdın kendisi, yani sabit
  tohumlu, seyrek, soluk, metnin arkasında duran bir alan (`Glyphs.tsx`).
  Başlıkta sadece 🍉, çünkü ürünün kendi adı. Her render'da değişen süs
  gürültüdür, tohum sabittir.
- Sayfayı kapatan kanıt şeridi ORTALI, rakam üstte yazı altında. Rakamı geniş
  bir boşlukla yazısından ayıran satır düzeni reddedildi.
- Sayfadaki her sayı ölçülmüş bir turdan gelir. Bir ölçüm ürününün vitrininde
  uydurma rakam, ürünün var olma sebebinin ihlalidir.
- Kaydırınca beliren bloklar ve sayan rakamlar Damla'nın istediği hareketlerdir,
  ama içerik HTML'de hazır durur (`noscript` stili) ve
  `prefers-reduced-motion` ilk karede bitmiş hali verir.

## açık borç

- Bu build sadece iki motor çağırabiliyor, perplexity ve anthropic. ChatGPT ve
  Gemini yok, ve ikisini eklemek canlı anahtarla doğrulama ister.
- `lulu rivals` tablosunda tür kelimeleri (API, AI, ML) gerçek adların üstünde
  duruyor. Kural konumsal ve korpus içi küçük harf kanıtına dayanıyor, bunlar o
  iki kapıdan da geçiyor. Okuyan insan kesiyor.
- Ad sayımı bir turda hiç cümle içinde geçmeyen ve imlasında iz taşımayan adı
  düşürür (4 Ağustos turunda `Twelve Data`).
- Perplexity artık `max_tokens` gönderiyor. Canlı anahtar olmadığı için
  DOĞRULANMADI.
- Rakip listesi hâlâ elle `--rivals`'a geçiriliyor. Tur listenin kaçırdığı
  adları basıyor ve konu dosyası artık adların hangi turdan ve hangi koldan
  geldiğini yazıyor, ama listeyi hâlâ kendisi kurmuyor.
