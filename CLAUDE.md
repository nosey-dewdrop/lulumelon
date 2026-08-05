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
- **Cümlenin içindeki tek kelime RENKLENDİRİLMEZ**, başlıkta da gövdede de.
  Renk kategori işaretler (ölçülen sayı pembe, ± lila), vurgu işaretlemez.
- **Vurgu PR'dır, dilbilgisi değil.** 5 Ağu'da iki yol denendi ve ikisi de
  reddedildi: başlıklarda lila kelime, sonra her başlıkta "pivot kelimenin"
  altını çizmek. İkincisi için Damla'nın sözü: "yine rastgele bir kelime türü
  seçip altını çizmişsin, PR yap, PR ruhun bu olsun." Kalınlaştırılan şey
  okuyucunun aklında kalmasını istediğin ŞEYDİR: sert sayı ("43.4% of the
  time", "12.6 points", "printed $0.0440 and paid $0.0467") ve satan iddia
  ("claim certainty of absence", "it does not"). Kelime türü seçip mekanik
  uygulamak vurgu değil, süstür.
- Kutu yok. Sayfadaki tek kutu terminaldir; ikinci bir çerçeve ya da dolgulu
  blok karttır ve reddedilir. Yuvarlak sadece gerçek dairelerde (terminalin
  üç noktası).
- Sayfanın tepesi TEK SATIR başlık, hemen altında terminal. Terminalin tek
  başına en üstte durması "çok sıkıcı" diye reddedildi (5 Ağu); başlığın
  altında bir blok halinde durması da reddedilmişti. Ölçü ikisinin arası:
  bir satır, sonra çalışan şeyin kendisi.
- **"Terminali küçült" KUTUYU küçültmektir, yazıyı değil.** 5 Ağu'da terminal
  metnini 11px'e indirdim ve reddedildi: okunmayan yazının kimseye faydası yok.
  Terminal metni 13px kalır, daralan şey kutunun genişliği ve yüksekliğidir.
- Tipografi: gövde 14.5px, ikincil 13px, kart başlığı 1.15rem, h1 1.3rem.
  5 Ağu'da iki uçtan da geçildi, Damla önce "eşek kadar" dedi sonra "çok küçük";
  bu satır o iki reddin arasında kalan ölçü.
- Emoji Damla'nın paletidir ve sabittir: 💞🎀✨💘🍉💫. Kırmızı kalp ASLA.
  Altısı TEK TEK yerleştirilir, her biri anlamına yakın bir yere: 🍉 başlıkta
  (ürünün adı), ✨ kaydın altındaki satırda, 💘 turun tarihinde, 💞 iki aralığı
  karşılaştıran kartta, 💫 zar kartında, 🎀 neyi reddettiğini sayan bölümde.
  İki yol denendi ve ikisi de reddedildi: altısını yan yana dizmek "lök",
  arka plana serpmek "tek tek değil". Her satırın başına emoji konmaz.
- Bloklar **✨🍉✨** ile ayrılır (`Frame.tsx` → `Divider`). Yatay çizgi yasak,
  ama bölme süsü Damla'nın isteği: "böyle çok kağıt gibi olmuş". Hep aynı üç
  glif, ortalı, seyrek harf aralıklı, ekran okuyucudan gizli.
- Navbar STICKY ve kağıt zeminli, altında çizgi yok, blur yok, gölge yok.
- Sayı ile yanındaki cümle AYNI satır yüksekliğini taşır, yoksa taban çizgisi
  kayar ve rakam cümlesinin altına düşer. Rakam sütunu sabit genişliktir
  (`w-[5.5rem]`), minimum değil, çünkü `$2.46` kendi satırını sağa itiyordu.
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
