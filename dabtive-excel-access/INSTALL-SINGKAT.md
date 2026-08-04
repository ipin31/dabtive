# Instalasi Singkat v0.5.1

```bash
unzip dabtive-excel-access-v0.5.1.zip
cd dabtive-excel-access
cp .env.example .env
nano .env
docker compose up -d --build
```

Login: `https://domain-anda/admin`

Setelah login:

1. **Upload File** → isi judul, deskripsi, fitur, jenis bisnis, screenshot, dan master `.xlsx`.
2. Screenshot dapat dipilih sekaligus, maksimal 8 gambar.
3. Pilih mode gratis atau centang **Produk Berbayar**.
4. **Homepage** → pilih **Disable katalog / single product** untuk MVP.
5. Pilih produk utama dan bagikan domain utama atau URL `/c/slug`.

Untuk upgrade, pertahankan `.env` dan volume lama. Jangan menjalankan `docker compose down -v`.
