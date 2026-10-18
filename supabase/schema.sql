-- =====================================================================
-- ĐIỂM TIN & LẮNG NGHE DƯ LUẬN — Bảng dữ liệu trên Supabase
-- Chạy toàn bộ file này 1 lần trong Supabase > SQL Editor > New query > Run
-- =====================================================================

create table if not exists public.dt_bai (
    khoa          text primary key,               -- mã bài (băm từ tiêu đề chuẩn hóa)
    muc           text[] not null default '{}',   -- các mục chứa bài: tieudiem, quocte, mxh, diaphuong, tuyengiao
    tieu_de       text not null,
    nguon         text,                           -- tên báo (lấy từ RSS)
    link_rss      text,                           -- link trong RSS (thường là link trung gian Google News)
    link_goc      text,                           -- link bài báo gốc sau khi giải mã
    tom_tat       text,                           -- sapo / tóm tắt
    cam_xuc       text not null default 'Trung lập',  -- Tích cực / Trung lập / Tiêu cực
    thoi_gian     timestamptz,                    -- thời gian đăng bài
    quet_luc      timestamptz not null default now(), -- lần cuối script quét thấy bài
    -- Phần nội dung "chế độ đọc"
    noi_dung      text,                           -- nội dung bài, các đoạn cách nhau bằng dòng trống
    anh           text,                           -- ảnh đại diện (og:image)
    trang_thai    text not null default 'cho',    -- cho / ok / loi
    so_lan_thu    int  not null default 0
);

create index if not exists dt_bai_muc_idx       on public.dt_bai using gin (muc);
create index if not exists dt_bai_thoi_gian_idx on public.dt_bai (thoi_gian desc);
create index if not exists dt_bai_quet_luc_idx  on public.dt_bai (quet_luc desc);

-- Bật bảo mật: ai cũng ĐỌC được (trang công khai), chỉ script quét (service_role) mới GHI được.
alter table public.dt_bai enable row level security;

drop policy if exists "dt_bai_doc_cong_khai" on public.dt_bai;
create policy "dt_bai_doc_cong_khai" on public.dt_bai
    for select to anon, authenticated using (true);

-- Không tạo policy insert/update/delete cho anon => trình duyệt không sửa được dữ liệu.
-- Script GitHub Actions dùng service_role key nên vượt qua RLS.
