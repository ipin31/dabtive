# Dabtive Excel Access v0.5.1

Aplikasi self-hosted untuk membuat landing page produk digital, mengumpulkan leads, dan membagikan file Excel dengan password berbeda untuk setiap user.


## Fix di v0.5.1

- Frontend produk desktop sekarang full-width tanpa card/border luar.
- Gallery kiri tetap sticky saat deskripsi kanan panjang.
- Export leads `.xlsx` dibuat ulang memakai OpenPyXL, bukan OOXML manual.
- Export divalidasi sebelum dikirim sehingga tidak memunculkan dialog repair di Microsoft Excel.
- Nomor WhatsApp dan email tetap dapat diklik di file export.
- Input yang diawali karakter formula diamankan agar tidak menjadi formula Excel.

## Yang baru di v0.5.1

- Frontend produk direvamp ke layout single-page yang ringkas seperti storefront digital product.
- Gallery berada di satu area dan mendukung maksimal 8 screenshot.
- Carousel mendukung arrow, dot navigation, keyboard, dan swipe pada mobile.
- Gallery sticky pada desktop ketika deskripsi atau form lebih panjang.
- Mobile menampilkan judul, preview, fitur, deskripsi, lalu form dalam satu alur yang ringkas.
- Product index homepage tetap tersedia, tetapi bisa dinonaktifkan untuk MVP melalui 301 redirect ke satu produk.
- Cover tunggal dari v0.4.0 otomatis dimigrasikan menjadi slide pertama.

## Flow produk gratis

1. Admin upload master `.xlsx`, copy landing page, fitur, dan beberapa screenshot.
2. User membuka landing page lalu mengisi nama, email, jenis bisnis, dan WhatsApp.
3. Sistem membuat License ID, password unik, serta salinan Excel terenkripsi.
4. User memperoleh halaman akses dan link download yang kedaluwarsa.

File hasil tetap `.xlsx` langsung, bukan ZIP.

## Flow produk berbayar — MVP tanpa payment webhook

1. Admin mencentang **Produk berbayar**, menentukan harga, payment link opsional, dan instruksi pembayaran.
2. User mengisi data pembeli.
3. Order dibuat dengan status `PENDING`; file belum dibuat.
4. Admin memeriksa pembayaran lalu klik **Tandai Lunas**.
5. Worker membuat Excel berpassword personal dan mengaktifkan link download.

Approval manual mencegah file terbuka hanya karena user memalsukan return URL payment link. Payment webhook otomatis dapat ditambahkan saat volume transaksi meningkat.

## Homepage / product index

Buka **Admin → Homepage**:

- **Disable katalog / single product**: `/` memakai HTTP 301 redirect ke produk utama.
- **Enable product index**: `/` menampilkan semua produk gratis dan berbayar yang aktif.

Untuk MVP satu produk, pertahankan mode pertama.

## Data yang tersedia di dashboard

Dashboard menampilkan seluruh requester berikut:

- Waktu request
- Nama
- Nomor WhatsApp
- Email
- Jenis bisnis
- Produk
- License ID
- Status pembayaran
- Status file
- Jumlah download

Seluruh data dapat diekspor langsung menjadi `.xlsx`.

## Landing page builder

Setiap produk mempunyai pengaturan:

- Judul dan deskripsi singkat
- Deskripsi panjang
- Daftar fitur, satu item per baris
- Maksimal 8 screenshot JPG, PNG, atau WEBP
- Master Excel `.xlsx`
- Pilihan jenis bisnis
- Mode gratis atau berbayar
- Harga, payment link, label CTA, dan instruksi pembayaran
- Masa aktif link dan batas download
- Status aktif/nonaktif landing page

## Instalasi

```bash
unzip dabtive-excel-access-v0.5.1.zip
cd dabtive-excel-access
cp .env.example .env
nano .env
docker compose up -d --build
```

Buka:

- Admin: `http://IP-SERVER:8000/admin`
- Public: `http://IP-SERVER:8000/`
- Health: `http://IP-SERVER:8000/health`

## Upgrade dari v0.4.0 atau v0.3.x

Versi ini memakai migrasi additive. Data campaign, leads, pembayaran, dan file lama tetap dipertahankan.

```bash
docker compose down
# backup .env, lalu timpa source dengan v0.5.1
docker compose up -d --build
```

Jangan menjalankan:

```bash
docker compose down -v
```

Opsi `-v` menghapus volume database dan storage aplikasi.

## Email opsional

Tanpa SMTP, sistem tetap berjalan dan password tampil pada halaman akses. Dengan SMTP aktif, link, License ID, dan password juga dikirim melalui email setelah file selesai dibuat.

## Backup

Backup kedua volume Docker:

- `postgres_data`: produk, leads, status pembayaran, dan statistik download.
- `app_data`: master Excel, screenshot produk, dan file hasil generate.

File hasil generate dibersihkan setelah link kedaluwarsa. Data leads tetap tersimpan.

## Pengujian yang disertakan

```bash
python tests/export_test.py
python tests/gallery_test.py
python tests/smoke_test.py
python tests/upgrade_test.py
python tests/web_flow_test.py
```
