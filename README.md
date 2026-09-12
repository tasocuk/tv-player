# TV Player — Philips 65PUS8949 (Titan OS)

Xtream Codes hesabınla çalışan, tek dosyalık HTML5 IPTV player.
Titan OS Chromium üstünde çalıştığı için televizyonda yerel uygulama gibi açılır.

* Ücretsiz, süre sınırı yok, reklam yok
* Kullanıcı adı/şifre **sadece TV'nin kendi belleğinde** tutulur (`localStorage`)
* Canlı TV + Filmler + Diziler + Favoriler, EPG bilgisi, kumanda navigasyonu

---

## Kumanda

| Tuş | İşlev |
|---|---|
| ▲ ▼ | Listede gezin · oynatıcıda kanal değiştir |
| ◀ ▶ | Kategoriler ↔ içerik listesi |
| OK | Seç · oynatıcıda bilgi çubuğu |
| Geri | Bir üst seviye · oynatıcıdan çık |
| Kırmızı veya 0 | Favorilere ekle / çıkar |

---

## Kurulum

İki yol var. **B şıkkı ile başla** — 5 dakika sürer ve her şeyin çalıştığını
doğrular. A şıkkı kalıcı kurulumdur.

### A) TV'de yerel uygulama olarak — DevView

DevView, Titan OS'un resmi geliştirici uygulamasıdır ve **tüm Titan OS
cihazlarında bulunur**. Kendi barındırdığın bir HTML5 uygulamasının URL'ini
televizyonda açmanı sağlar.

1. Bilgisayardan [partners.titanos.tv](https://partners.titanos.tv) adresine gir,
   hesap aç. DevView bölümünde erişim yoksa **talep et** — inceleyip açıyorlar.
2. Portalda **DevView / Sandbox** bölümüne uygulamanı ekle ve URL'ini gir.
3. **Device Management**'tan televizyonu eşleştir.
4. TV'de DevView'i aç → uygulaman açılır.
5. DevView'i ana ekranda favorilere sabitle. Son URL'i hatırladığı için
   günlük kullanım iki tık olur.

> Uygulamayı nereye koyacaksın? Sağlayıcın **https** destekliyorsa
> GitHub Pages bedava ve yeterli (aşağıda). Desteklemiyorsa **http** ile
> yayınlaman gerekir — B şıkkındaki `proxy.py` bunu da hallediyor.

### B) Bilgisayardan — hemen test

```bash
python3 proxy.py --upstream http://SUNUCU:PORT
```

Ekrana yazdığı adresi (`http://192.168.x.x:8099/`) TV'nin tarayıcısında,
telefonda veya bilgisayarda aç. Player'daki **Sunucu adresi** alanına da
aynı adresi yaz.

`proxy.py` üç işi birden yapar: player'ı servis eder, CORS başlıklarını ekler,
ve https/http karışıklığını ortadan kaldırır. Ek paket gerekmez, sadece Python 3.

---

## GitHub Pages'e koymak (ücretsiz barındırma)

```bash
git init && git add . && git commit -m "tv player"
git branch -M main
git remote add origin https://github.com/KULLANICI/tv-player.git
git push -u origin main
```

GitHub → Settings → Pages → Source: `main` / root → Save.
Adresin: `https://KULLANICI.github.io/tv-player/`

**Depoyu private yap.** Player'ın içinde şifre yok ama gereksiz yere
herkese açık olmasına gerek de yok. (Pages private depoda ücretli olabilir;
o durumda public bırak — dosyada kimlik bilgisi bulunmuyor.)

---

## Sorun giderme

Player bağlanamazsa giriş ekranı sorunu **teşhis edip yazar**. Sık görülenler:

| Belirti | Sebep | Çözüm |
|---|---|---|
| "Sayfa https ama sunucun http" | Mixed content engeli | `proxy.py` kullan veya sağlayıcının https adresini iste |
| "Sunucuya ulaşılamadı" | Sunucu CORS izni vermiyor | `proxy.py` kullan |
| "Kullanıcı adı veya şifre hatalı" | Bilgiler yanlış veya abonelik bitmiş | Bilgileri kontrol et |
| Liste geliyor, görüntü açılmıyor | Panel `.m3u8` vermiyor | Player otomatik `.ts`'e düşer; olmazsa `proxy.py` dene |
| Görüntü takılıyor | Ağ / sunucu yavaş | TV'yi kabloyla bağla |

Ayarları sıfırlamak için tarayıcı konsolunda: `resetPlayer()`

---

## Dosyalar

```
index.html   Player (tek dosya, bağımlılıklar CDN'den)
proxy.py     CORS + HTTP proxy ve yerel sunucu (opsiyonel)
README.md    Bu dosya
```

`index.html` içinde `hls.js` (HLS akışları) ve `mpegts.js` (`.ts` akışları)
jsDelivr CDN'inden yüklenir. İnternetsiz çalışması gerekirse iki dosyayı
indirip `<script src>` yollarını yerel dosyalara çevir.
