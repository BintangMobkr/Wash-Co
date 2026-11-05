# Wash&Co - Sistem Pencatatan Laundry

Aplikasi sederhana untuk mencatat pesanan laundry Wash&Co. Dibuat dengan
**Streamlit** dan **SQLite**, tanpa fitur login.

## Menjalankan aplikasi

```powershell
.\.venv\Scripts\streamlit.exe run app.py
```

Buka http://localhost:8501.

Jika environment belum ada:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Fitur

- **Dashboard owner**
  - Ringkasan jumlah pesanan, pesanan yang diproses, pendapatan lunas, dan piutang.
  - Daftar pesanan dengan filter status, metode bayar, dan pencarian.
  - Grafik pendapatan lunas per tanggal.
  - Ubah status pesanan (`Baru`, `Dicuci`, `Siap diambil`, `Sudah diambil`)
    dan status pembayaran (`Belum bayar`, `Lunas`).
  - Kelola tarif dan durasi layanan.
- **Pesanan baru**
  - Identitas pelanggan: nama, nomor telepon/WhatsApp, alamat, jenis pelanggan.
  - Pilih satu atau beberapa paket cuci, berat cucian, ambil di outlet atau
    antar ke alamat (Rp7.000/kg).
  - Pembayaran Cash atau QRIS; gambar QRIS muncul saat memilih QRIS.
  - Total biaya dan estimasi selesai dihitung otomatis.
- **Pelanggan**
  - Daftar pelanggan, jumlah pesanan, total belanja, dan pesanan terakhir.
- **Struk**
  - Struk pesanan lengkap dan unduh struk dalam format `.pdf`.

## Tarif awal

| Layanan | Tarif | Estimasi |
|---|---|---|
| Cuci | Rp7.000/kg | 3 hari |
| Cuci Setrika | Rp10.000/kg | 3-5 hari |
| Cuci Setrika Kilat | Rp15.000/kg | 1 hari |
| Antar ke alamat | Rp7.000/kg | - |

Tarif dapat diubah dari dashboard owner. Perubahan tarif hanya berlaku untuk
pesanan baru; pesanan lama tetap memakai tarif saat pesanan dibuat.

## Struktur data

- `pelanggan` - data pelanggan unik berdasarkan nomor telepon.
- `layanan` - paket cuci, tarif per kg, dan durasi.
- `pesanan` - header pesanan, pembayaran, status, dan total.
- `detail_pesanan` - rincian layanan per pesanan (mendukung lebih dari satu
  layanan dalam satu transaksi).

Database dibuat otomatis di `washco.db` saat aplikasi pertama dijalankan.
