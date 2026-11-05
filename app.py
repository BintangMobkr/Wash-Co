"""Wash&Co - aplikasi pencatatan laundry (Streamlit + SQLite)."""

import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "washco.db"
QRIS_IMAGE = BASE_DIR / "assets" / "qris.png"

TARIF_ANTAR = 7_000
STATUS_PESANAN = ["Baru", "Dicuci", "Siap diambil", "Sudah diambil"]
STATUS_BAYAR = ["Belum bayar", "Lunas"]
METODE_BAYAR = ["Cash", "QRIS"]
JENIS_PELANGGAN = ["Umum", "Mahasiswa", "Pelajar", "Karyawan"]
BULAN = [
    "Jan", "Feb", "Mar", "Apr", "Mei", "Jun",
    "Jul", "Agu", "Sep", "Okt", "Nov", "Des",
]

st.set_page_config(
    page_title="Wash&Co - Pencatatan Laundry",
    page_icon="🧺",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px;}
        h1, h2, h3 {color: #1f2937;}
        .washco-title {
            font-size: 2.6rem; font-weight: 800; letter-spacing: -1.5px;
            line-height: 1.1; color: #1f2937; margin-bottom: 0;
        }
        .washco-sub {color: #6b7280; margin-top: .15rem; margin-bottom: 1.6rem;}
        [data-testid="stMetric"] {
            background: #ffffff; border: 1px solid #e5e7eb;
            padding: 14px 16px; border-radius: 12px;
        }
        [data-testid="stMetricValue"] {font-size: 1.55rem;}
        div[data-testid="stExpander"] {border: 1px solid #e5e7eb; border-radius: 10px;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pelanggan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nama TEXT NOT NULL,
                telepon TEXT NOT NULL UNIQUE,
                alamat TEXT NOT NULL DEFAULT '',
                jenis TEXT NOT NULL DEFAULT 'Umum',
                dibuat_pada TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS layanan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nama TEXT NOT NULL UNIQUE,
                harga_per_kg INTEGER NOT NULL,
                durasi_hari INTEGER NOT NULL DEFAULT 1,
                keterangan TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS pesanan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kode TEXT NOT NULL UNIQUE,
                pelanggan_id INTEGER NOT NULL,
                berat REAL NOT NULL,
                pengambilan TEXT NOT NULL,
                biaya_antar INTEGER NOT NULL DEFAULT 0,
                metode_bayar TEXT NOT NULL,
                status_bayar TEXT NOT NULL DEFAULT 'Belum bayar',
                status_pesanan TEXT NOT NULL DEFAULT 'Baru',
                total INTEGER NOT NULL,
                tanggal_masuk TEXT NOT NULL,
                estimasi_selesai TEXT NOT NULL,
                catatan TEXT NOT NULL DEFAULT '',
                dibuat_pada TEXT NOT NULL,
                FOREIGN KEY (pelanggan_id) REFERENCES pelanggan (id)
            );

            CREATE TABLE IF NOT EXISTS detail_pesanan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pesanan_id INTEGER NOT NULL,
                layanan_id INTEGER NOT NULL,
                harga_per_kg INTEGER NOT NULL,
                FOREIGN KEY (pesanan_id) REFERENCES pesanan (id) ON DELETE CASCADE,
                FOREIGN KEY (layanan_id) REFERENCES layanan (id)
            );

            CREATE INDEX IF NOT EXISTS idx_pesanan_pelanggan
                ON pesanan (pelanggan_id);
            CREATE INDEX IF NOT EXISTS idx_detail_pesanan
                ON detail_pesanan (pesanan_id);
            """
        )
        jumlah_layanan = conn.execute("SELECT COUNT(*) FROM layanan").fetchone()[0]
        if jumlah_layanan == 0:
            conn.executemany(
                """
                INSERT INTO layanan (nama, harga_per_kg, durasi_hari, keterangan)
                VALUES (?, ?, ?, ?)
                """,
                [
                    ("Cuci", 7_000, 3, "Cuci bersih, selesai 3 hari"),
                    ("Cuci Setrika", 10_000, 4, "Cuci dan setrika, selesai 3-5 hari"),
                    ("Cuci Setrika Kilat", 15_000, 1, "Cuci setrika ekspres, selesai 1 hari"),
                ],
            )
        conn.commit()
    finally:
        conn.close()


def get_layanan():
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM layanan ORDER BY id").fetchall()
    finally:
        conn.close()


def get_orders():
    conn = get_conn()
    try:
        return conn.execute(
            """
            SELECT p.*, pl.nama, pl.telepon, pl.alamat, pl.jenis,
                   GROUP_CONCAT(l.nama, ', ') AS daftar_layanan
            FROM pesanan p
            JOIN pelanggan pl ON pl.id = p.pelanggan_id
            JOIN detail_pesanan d ON d.pesanan_id = p.id
            JOIN layanan l ON l.id = d.layanan_id
            GROUP BY p.id
            ORDER BY p.id DESC
            """
        ).fetchall()
    finally:
        conn.close()


def get_order_by_kode(kode):
    conn = get_conn()
    try:
        return conn.execute(
            """
            SELECT p.*, pl.nama, pl.telepon, pl.alamat, pl.jenis,
                   GROUP_CONCAT(l.nama, ', ') AS daftar_layanan
            FROM pesanan p
            JOIN pelanggan pl ON pl.id = p.pelanggan_id
            JOIN detail_pesanan d ON d.pesanan_id = p.id
            JOIN layanan l ON l.id = d.layanan_id
            WHERE p.kode = ?
            GROUP BY p.id
            """,
            (kode,),
        ).fetchone()
    finally:
        conn.close()


def get_order_details(pesanan_id):
    conn = get_conn()
    try:
        return conn.execute(
            """
            SELECT d.harga_per_kg, l.nama
            FROM detail_pesanan d
            JOIN layanan l ON l.id = d.layanan_id
            WHERE d.pesanan_id = ?
            ORDER BY d.id
            """,
            (pesanan_id,),
        ).fetchall()
    finally:
        conn.close()


def get_pelanggan_summary():
    conn = get_conn()
    try:
        return conn.execute(
            """
            SELECT pl.*,
                   COUNT(p.id) AS jumlah_pesanan,
                   COALESCE(SUM(CASE WHEN p.status_bayar = 'Lunas'
                                     THEN p.total ELSE 0 END), 0) AS total_belanja,
                   MAX(p.tanggal_masuk) AS terakhir_pesanan
            FROM pelanggan pl
            LEFT JOIN pesanan p ON p.pelanggan_id = pl.id
            GROUP BY pl.id
            ORDER BY pl.nama COLLATE NOCASE
            """
        ).fetchall()
    finally:
        conn.close()


def simpan_pesanan(
    nama,
    telepon,
    alamat,
    jenis,
    layanan_terpilih,
    berat,
    antar,
    metode_bayar,
    sudah_bayar,
    catatan,
):
    """Simpan pelanggan, pesanan, dan rincian layanan. Mengembalikan kode pesanan."""
    sekarang = datetime.now().replace(microsecond=0)
    tanggal_masuk = sekarang.date()
    estimasi = tanggal_masuk + timedelta(
        days=max(layanan["durasi_hari"] for layanan in layanan_terpilih)
    )

    biaya_layanan = int(
        round(sum(layanan["harga_per_kg"] for layanan in layanan_terpilih) * berat)
    )
    biaya_antar = int(round(TARIF_ANTAR * berat)) if antar else 0
    total = biaya_layanan + biaya_antar

    conn = get_conn()
    try:
        cur = conn.cursor()
        pelanggan = cur.execute(
            "SELECT id FROM pelanggan WHERE telepon = ?", (telepon,)
        ).fetchone()

        if pelanggan:
            pelanggan_id = pelanggan["id"]
            cur.execute(
                "UPDATE pelanggan SET nama = ?, alamat = ?, jenis = ? WHERE id = ?",
                (nama, alamat, jenis, pelanggan_id),
            )
        else:
            pelanggan_id = cur.execute(
                """
                INSERT INTO pelanggan (nama, telepon, alamat, jenis, dibuat_pada)
                VALUES (?, ?, ?, ?, ?)
                """,
                (nama, telepon, alamat, jenis, sekarang.isoformat()),
            ).lastrowid

        next_id = cur.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 FROM pesanan"
        ).fetchone()[0]
        kode = f"WC-{next_id:04d}"

        pesanan_id = cur.execute(
            """
            INSERT INTO pesanan (
                kode, pelanggan_id, berat, pengambilan, biaya_antar,
                metode_bayar, status_bayar, status_pesanan, total,
                tanggal_masuk, estimasi_selesai, catatan, dibuat_pada
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Baru', ?, ?, ?, ?, ?)
            """,
            (
                kode,
                pelanggan_id,
                berat,
                "Antar ke alamat" if antar else "Ambil di outlet",
                biaya_antar,
                metode_bayar,
                "Lunas" if sudah_bayar else "Belum bayar",
                total,
                tanggal_masuk.isoformat(),
                estimasi.isoformat(),
                catatan,
                sekarang.isoformat(),
            ),
        ).lastrowid

        cur.executemany(
            """
            INSERT INTO detail_pesanan (pesanan_id, layanan_id, harga_per_kg)
            VALUES (?, ?, ?)
            """,
            [
                (pesanan_id, layanan["id"], layanan["harga_per_kg"])
                for layanan in layanan_terpilih
            ],
        )
        conn.commit()
        return kode
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------
def rupiah(nilai):
    return "Rp" + f"{int(round(nilai)):,}".replace(",", ".")


def tanggal_indo(iso):
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{d.day:02d} {BULAN[d.month - 1]} {d.year}"
    except (ValueError, TypeError):
        return str(iso)


def waktu_indo(stamp):
    try:
        return datetime.fromisoformat(str(stamp)).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return str(stamp)


def normalisasi_telepon(nomor):
    angka = re.sub(r"\D", "", nomor or "")
    if angka.startswith("62"):
        angka = "0" + angka[2:]
    return angka


def label_layanan(layanan):
    return (
        f"{layanan['nama']} - {rupiah(layanan['harga_per_kg'])}/kg "
        f"(selesai {layanan['durasi_hari']} hari)"
    )


# ---------------------------------------------------------------------------
# Komponen halaman
# ---------------------------------------------------------------------------
def render_struk(kode):
    order = get_order_by_kode(kode)
    if order is None:
        st.warning("Pesanan tidak ditemukan.")
        return

    details = get_order_details(order["id"])
    biaya_layanan = sum(
        int(round(detail["harga_per_kg"] * order["berat"])) for detail in details
    )

    with st.container(border=True):
        st.markdown(
            "<h2 style='text-align:center; margin-bottom:0;'>Wash&amp;Co</h2>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<p style='text-align:center; color:#6b7280; margin-top:0;'>"
            "Struk laundry</p>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"Kode {order['kode']} · dibuat {waktu_indo(order['dibuat_pada'])}"
        )
        st.divider()

        kiri, kanan = st.columns(2)
        with kiri:
            st.markdown(f"**Pelanggan**  \n{order['nama']}")
            st.markdown(f"**Telepon / WhatsApp**  \n{order['telepon']}")
        with kanan:
            st.markdown(f"**Alamat**  \n{order['alamat']}")
            st.markdown(f"**Jenis pelanggan**  \n{order['jenis']}")

        st.divider()
        st.markdown("**Rincian layanan**")
        tabel = pd.DataFrame(
            [
                {
                    "Layanan": detail["nama"],
                    "Harga/kg": rupiah(detail["harga_per_kg"]),
                    "Berat": f"{order['berat']:.1f} kg",
                    "Subtotal": rupiah(detail["harga_per_kg"] * order["berat"]),
                }
                for detail in details
            ]
        )
        st.table(tabel)

        st.divider()
        kiri, kanan = st.columns([2, 1])
        with kiri:
            st.write(f"Biaya layanan: **{rupiah(biaya_layanan)}**")
            st.write(f"Biaya antar: **{rupiah(order['biaya_antar'])}**")
            st.write(f"Estimasi selesai: **{tanggal_indo(order['estimasi_selesai'])}**")
            st.write(f"Status pesanan: **{order['status_pesanan']}**")
            st.write(
                f"Pembayaran: **{order['metode_bayar']} · {order['status_bayar']}**"
            )
            if order["catatan"]:
                st.write(f"Catatan: **{order['catatan']}**")
        with kanan:
            st.metric("Total", rupiah(order["total"]))

    st.download_button(
        "Unduh struk (.txt)",
        data=buat_teks_struk(order, details),
        file_name=f"struk-{order['kode']}.txt",
        mime="text/plain",
        key=f"unduh_{order['kode']}",
    )


def buat_teks_struk(order, details):
    garis = "=" * 46
    lines = [
        garis,
        "                 WASH&CO",
        "     Pemesanan dan pencatatan laundry",
        garis,
        f"Kode pesanan : {order['kode']}",
        f"Tanggal      : {waktu_indo(order['dibuat_pada'])}",
        f"Pelanggan    : {order['nama']}",
        f"Telepon      : {order['telepon']}",
        f"Alamat       : {order['alamat']}",
        f"Jenis        : {order['jenis']}",
        "-" * 46,
        "Rincian layanan:",
    ]
    for detail in details:
        subtotal = int(round(detail["harga_per_kg"] * order["berat"]))
        lines.append(
            f"- {detail['nama']} ({rupiah(detail['harga_per_kg'])}/kg "
            f"x {order['berat']:.1f} kg) = {rupiah(subtotal)}"
        )
    lines.extend(
        [
            "-" * 46,
            f"Biaya layanan : {rupiah(order['total'] - order['biaya_antar'])}",
            f"Biaya antar   : {rupiah(order['biaya_antar'])}",
            f"TOTAL         : {rupiah(order['total'])}",
            f"Metode bayar  : {order['metode_bayar']} ({order['status_bayar']})",
            f"Status        : {order['status_pesanan']}",
            f"Estimasi      : {tanggal_indo(order['estimasi_selesai'])}",
            f"Catatan       : {order['catatan'] or '-'}",
            garis,
            "Terima kasih telah menggunakan layanan Wash&Co.",
            garis,
        ]
    )
    return "\n".join(lines)


def render_dashboard():
    if st.session_state.get("owner_flash"):
        st.success(st.session_state.pop("owner_flash"))

    orders = get_orders()
    total_pesanan = len(orders)
    aktif = sum(1 for o in orders if o["status_pesanan"] != "Sudah diambil")
    pendapatan = sum(o["total"] for o in orders if o["status_bayar"] == "Lunas")
    belum_bayar = sum(o["total"] for o in orders if o["status_bayar"] != "Lunas")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total pesanan", total_pesanan)
    c2.metric("Masih diproses", aktif)
    c3.metric("Pendapatan (lunas)", rupiah(pendapatan))
    c4.metric("Belum dibayar", rupiah(belum_bayar))

    st.markdown("### Daftar pesanan")

    if not orders:
        st.info(
            "Belum ada pesanan. Buat pesanan pertama dari tab **Pesanan baru**."
        )
    else:
        data = pd.DataFrame(
            {
                "Kode": [o["kode"] for o in orders],
                "Tanggal": [tanggal_indo(o["tanggal_masuk"]) for o in orders],
                "Pelanggan": [o["nama"] for o in orders],
                "Telepon": [o["telepon"] for o in orders],
                "Layanan": [o["daftar_layanan"] for o in orders],
                "Berat": [o["berat"] for o in orders],
                "Antar": [o["biaya_antar"] for o in orders],
                "Metode": [o["metode_bayar"] for o in orders],
                "Pembayaran": [o["status_bayar"] for o in orders],
                "Status": [o["status_pesanan"] for o in orders],
                "Total": [o["total"] for o in orders],
                "Tanggal ISO": [o["tanggal_masuk"] for o in orders],
            }
        )

        f1, f2, f3 = st.columns([1.2, 1.2, 2])
        filter_status = f1.selectbox(
            "Status pesanan",
            ["Semua"] + STATUS_PESANAN,
            key="filter_status",
        )
        filter_metode = f2.selectbox(
            "Metode bayar",
            ["Semua"] + METODE_BAYAR,
            key="filter_metode",
        )
        cari = f3.text_input(
            "Cari kode / nama / telepon",
            key="cari_owner",
            placeholder="Contoh: WC-0001 atau kia",
        )

        filtered = data.copy()
        if filter_status != "Semua":
            filtered = filtered[filtered["Status"] == filter_status]
        if filter_metode != "Semua":
            filtered = filtered[filtered["Metode"] == filter_metode]
        if cari.strip():
            teks = cari.strip().lower()
            gabungan = (
                filtered["Kode"].astype(str)
                + " "
                + filtered["Pelanggan"].astype(str)
                + " "
                + filtered["Telepon"].astype(str)
            )
            filtered = filtered[
                gabungan.str.lower().str.contains(teks, regex=False)
            ]

        if filtered.empty:
            st.info("Tidak ada pesanan yang sesuai filter.")
        else:
            tampil = filtered.drop(columns=["Tanggal ISO"]).copy()
            tampil["Berat"] = tampil["Berat"].map(lambda x: f"{float(x):.1f} kg")
            tampil["Antar"] = tampil["Antar"].map(
                lambda x: rupiah(x) if x else "Gratis"
            )
            tampil["Total"] = tampil["Total"].map(rupiah)
            st.dataframe(tampil, hide_index=True, width="stretch")
            st.caption(f"{len(filtered)} pesanan ditampilkan")

            lunas = filtered[filtered["Pembayaran"] == "Lunas"]
            if not lunas.empty:
                st.markdown("### Pendapatan lunas per tanggal")
                grafik = lunas.groupby("Tanggal ISO")["Total"].sum()
                st.bar_chart(grafik, color="#FF4B4B")

        with st.expander("Ubah status pesanan"):
            peta_pesanan = {
                f"{o['kode']} - {o['nama']}": o for o in orders
            }
            label = st.selectbox(
                "Pilih pesanan",
                list(peta_pesanan.keys()),
                key="ubah_pesanan",
            )
            pesanan = peta_pesanan[label]

            kiri, kanan = st.columns(2)
            status_sekarang = (
                STATUS_PESANAN.index(pesanan["status_pesanan"])
                if pesanan["status_pesanan"] in STATUS_PESANAN
                else 0
            )
            bayar_sekarang = (
                STATUS_BAYAR.index(pesanan["status_bayar"])
                if pesanan["status_bayar"] in STATUS_BAYAR
                else 0
            )
            status_baru = kiri.selectbox(
                "Status pesanan",
                STATUS_PESANAN,
                index=status_sekarang,
                key=f"status_{pesanan['id']}",
            )
            bayar_baru = kanan.selectbox(
                "Status pembayaran",
                STATUS_BAYAR,
                index=bayar_sekarang,
                key=f"bayar_{pesanan['id']}",
            )

            if st.button(
                "Simpan perubahan",
                type="primary",
                key="ubah_status",
            ):
                conn = get_conn()
                try:
                    conn.execute(
                        """
                        UPDATE pesanan
                        SET status_pesanan = ?, status_bayar = ?
                        WHERE id = ?
                        """,
                        (status_baru, bayar_baru, pesanan["id"]),
                    )
                    conn.commit()
                finally:
                    conn.close()
                st.session_state["owner_flash"] = (
                    f"Pesanan {pesanan['kode']} berhasil diperbarui."
                )
                st.rerun()

    with st.expander("Kelola tarif layanan"):
        st.caption("Perubahan tarif hanya berlaku untuk pesanan baru.")
        layanan_list = get_layanan()
        with st.form("form_tarif"):
            perubahan = []
            for layanan in layanan_list:
                kolom_nama, kolom_harga, kolom_durasi = st.columns([2, 1, 1])
                kolom_nama.markdown(f"**{layanan['nama']}**")
                harga = kolom_harga.number_input(
                    "Harga/kg",
                    min_value=500,
                    max_value=100_000,
                    step=500,
                    value=int(layanan["harga_per_kg"]),
                    key=f"tarif_{layanan['id']}",
                )
                durasi = kolom_durasi.number_input(
                    "Durasi (hari)",
                    min_value=1,
                    max_value=30,
                    value=int(layanan["durasi_hari"]),
                    key=f"durasi_{layanan['id']}",
                )
                perubahan.append((harga, durasi, layanan["id"]))

            if st.form_submit_button("Simpan tarif", type="primary"):
                conn = get_conn()
                try:
                    conn.executemany(
                        """
                        UPDATE layanan
                        SET harga_per_kg = ?, durasi_hari = ?
                        WHERE id = ?
                        """,
                        perubahan,
                    )
                    conn.commit()
                finally:
                    conn.close()
                st.session_state["owner_flash"] = "Tarif layanan berhasil diperbarui."
                st.rerun()


def render_pesanan_baru():
    layanan_list = get_layanan()
    if not layanan_list:
        st.warning("Belum ada layanan. Atur layanan dari dashboard owner.")
        return

    peta_layanan = {layanan["id"]: layanan for layanan in layanan_list}

    st.markdown("### Identitas pelanggan")
    kiri, kanan = st.columns(2)
    nama = kiri.text_input(
        "Nama pelanggan",
        placeholder="Nama lengkap",
        key="order_nama",
    )
    telepon_input = kanan.text_input(
        "Nomor telepon / WhatsApp",
        placeholder="08xxxxxxxxxx",
        key="order_telepon",
    )
    alamat = st.text_area(
        "Alamat pelanggan",
        placeholder="Alamat lengkap",
        height=80,
        key="order_alamat",
    )
    jenis = st.selectbox(
        "Jenis pelanggan",
        JENIS_PELANGGAN,
        key="order_jenis",
    )
    st.caption(
        "Nomor telepon yang sudah terdaftar akan otomatis memakai data pelanggan "
        "yang ada."
    )

    st.markdown("### Detail layanan")
    pilihan_layanan = st.multiselect(
        "Paket cuci (bisa pilih lebih dari satu)",
        options=list(peta_layanan.keys()),
        default=[layanan_list[0]["id"]],
        format_func=lambda id_layanan: label_layanan(peta_layanan[id_layanan]),
        key="order_layanan",
    )
    berat = st.number_input(
        "Berat cucian (kg)",
        min_value=0.1,
        max_value=100.0,
        value=1.0,
        step=0.1,
        format="%.1f",
        key="order_berat",
    )
    pengambilan = st.radio(
        "Pengambilan pakaian",
        [
            "Ambil di outlet (gratis)",
            f"Antar ke alamat (+{rupiah(TARIF_ANTAR)}/kg)",
        ],
        horizontal=True,
        key="order_pengambilan",
    )
    antar = pengambilan.startswith("Antar")

    st.markdown("### Pembayaran")
    metode = st.radio(
        "Metode pembayaran",
        METODE_BAYAR,
        horizontal=True,
        key="order_metode",
    )
    sudah_bayar = st.checkbox(
        "Pembayaran sudah diterima (lunas)",
        value=True,
        help=(
            "Jika belum dibayar, status pembayaran menjadi Belum bayar dan dapat "
            "diubah dari dashboard owner."
        ),
        key="order_sudah_bayar",
    )

    if metode == "QRIS":
        _, tengah, _ = st.columns([1, 1, 1])
        with tengah:
            if QRIS_IMAGE.exists():
                st.image(
                    str(QRIS_IMAGE),
                    caption="QRIS Wash&Co - scan untuk membayar",
                    width=280,
                )
            else:
                st.warning("Gambar QRIS belum tersedia.")
        st.caption("Scan QRIS untuk membayar sesuai total pesanan di bawah.")

    layanan_terpilih = [
        peta_layanan[id_layanan] for id_layanan in pilihan_layanan
    ]
    biaya_layanan = int(
        round(sum(layanan["harga_per_kg"] for layanan in layanan_terpilih) * berat)
    )
    biaya_antar = int(round(TARIF_ANTAR * berat)) if antar else 0
    total = biaya_layanan + biaya_antar

    estimasi = date.today() + timedelta(
        days=max((layanan["durasi_hari"] for layanan in layanan_terpilih), default=1)
    )
    catatan = st.text_input(
        "Catatan (opsional)",
        placeholder="Contoh: pisahkan pakaian putih",
        key="order_catatan",
    )

    with st.container(border=True):
        st.markdown("#### Ringkasan pembayaran")
        kiri, kanan = st.columns([3, 1])
        with kiri:
            if layanan_terpilih:
                for layanan in layanan_terpilih:
                    st.write(
                        f"{layanan['nama']} · {rupiah(layanan['harga_per_kg'])}/kg "
                        f"× {berat:.1f} kg"
                    )
            else:
                st.write("Belum ada paket cuci yang dipilih.")
            if antar:
                st.write(
                    f"Antar ke alamat · {rupiah(TARIF_ANTAR)}/kg × {berat:.1f} kg"
                )
            st.caption(f"Estimasi selesai: {tanggal_indo(estimasi)}")
        with kanan:
            st.metric("Total", rupiah(total))

    if st.button(
        "Simpan pesanan",
        type="primary",
        width="stretch",
        key="simpan_pesanan",
    ):
        telepon = normalisasi_telepon(telepon_input)
        errors = []
        if len(nama.strip()) < 2:
            errors.append("Nama pelanggan minimal 2 karakter.")
        if not (9 <= len(telepon) <= 15):
            errors.append("Nomor telepon / WhatsApp harus 9-15 digit angka.")
        if not alamat.strip():
            errors.append("Alamat pelanggan wajib diisi.")
        if not layanan_terpilih:
            errors.append("Pilih minimal satu paket cuci.")

        if errors:
            for pesan in errors:
                st.error(pesan)
        else:
            kode = simpan_pesanan(
                nama=nama.strip(),
                telepon=telepon,
                alamat=alamat.strip(),
                jenis=jenis,
                layanan_terpilih=layanan_terpilih,
                berat=berat,
                antar=antar,
                metode_bayar=metode,
                sudah_bayar=sudah_bayar,
                catatan=catatan.strip(),
            )
            st.session_state["last_order_kode"] = kode
            st.session_state["order_flash"] = (
                f"Pesanan {kode} berhasil disimpan. "
                "Struk dapat dilihat pada tab **Struk**."
            )
            st.rerun()


def render_pelanggan():
    st.markdown("### Data pelanggan")
    cari = st.text_input(
        "Cari nama atau nomor telepon",
        placeholder="Ketik nama atau nomor telepon",
        key="cari_pelanggan",
    )

    pelanggan_list = get_pelanggan_summary()
    if not pelanggan_list:
        st.info(
            "Belum ada pelanggan. Data pelanggan otomatis tersimpan saat pesanan "
            "dibuat."
        )
        return

    data = pd.DataFrame(
        {
            "Nama": [p["nama"] for p in pelanggan_list],
            "Telepon": [p["telepon"] for p in pelanggan_list],
            "Alamat": [p["alamat"] for p in pelanggan_list],
            "Jenis": [p["jenis"] for p in pelanggan_list],
            "Jumlah pesanan": [p["jumlah_pesanan"] for p in pelanggan_list],
            "Total belanja": [p["total_belanja"] for p in pelanggan_list],
            "Terakhir pesanan": [
                tanggal_indo(p["terakhir_pesanan"]) if p["terakhir_pesanan"] else "-"
                for p in pelanggan_list
            ],
        }
    )

    if cari.strip():
        teks = cari.strip().lower()
        gabungan = data["Nama"].astype(str) + " " + data["Telepon"].astype(str)
        data = data[gabungan.str.lower().str.contains(teks, regex=False)]

    if data.empty:
        st.info("Pelanggan tidak ditemukan.")
        return

    tampil = data.copy()
    tampil["Total belanja"] = tampil["Total belanja"].map(rupiah)
    st.dataframe(tampil, hide_index=True, width="stretch")
    st.caption(f"{len(tampil)} pelanggan")


def render_struk_tab():
    orders = get_orders()
    if not orders:
        st.info(
            "Belum ada pesanan. Struk akan muncul otomatis setelah pesanan dibuat."
        )
        return

    label = {
        o["kode"]: f"{o['kode']} · {o['nama']} · {tanggal_indo(o['tanggal_masuk'])}"
        for o in orders
    }
    kode_list = list(label.keys())
    last_order = st.session_state.get("last_order_kode")
    default_index = kode_list.index(last_order) if last_order in kode_list else 0

    pilihan = st.selectbox(
        "Pilih pesanan",
        kode_list,
        index=default_index,
        format_func=lambda kode: label[kode],
        key=f"struk_pilih_{last_order or 'awal'}",
    )
    render_struk(pilihan)


# ---------------------------------------------------------------------------
# Aplikasi
# ---------------------------------------------------------------------------
init_db()

st.markdown('<div class="washco-title">Wash&amp;Co</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="washco-sub">Pemesanan dan pencatatan laundry</div>',
    unsafe_allow_html=True,
)

if st.session_state.get("order_flash"):
    st.success(st.session_state.pop("order_flash"))

tab_owner, tab_baru, tab_pelanggan, tab_struk = st.tabs(
    ["Dashboard owner", "Pesanan baru", "Pelanggan", "Struk"]
)

with tab_owner:
    render_dashboard()

with tab_baru:
    render_pesanan_baru()

with tab_pelanggan:
    render_pelanggan()

with tab_struk:
    render_struk_tab()

st.caption("Wash&Co · Sistem pencatatan laundry · Data tersimpan di washco.db")
