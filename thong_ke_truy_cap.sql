-- =====================================================================
-- THỐNG KÊ LƯỢT TRUY CẬP cho trang Hệ sinh thái 4.0
-- Chạy 1 lần trong Supabase (project elkysoeukqtweytkekwr) > SQL Editor > Run.
--
-- Trang chỉ nhận về SỐ LIỆU ĐÃ CỘNG GỘP theo ngày, không đọc được từng dòng
-- truy cập. Bảng thong_ke_truy_cap vẫn giữ quyền "chỉ được thêm" như cũ.
-- =====================================================================

-- Bảng đã có từ app Điểm tin; lệnh này chỉ để chắc chắn
create table if not exists public.thong_ke_truy_cap (
    id         bigint generated always as identity primary key,
    ten_app    text,
    thoi_gian  timestamptz not null default now()
);
create index if not exists thong_ke_truy_cap_thoi_gian_idx on public.thong_ke_truy_cap (thoi_gian);

-- Số lượt theo ngày (giờ Việt Nam) và theo ứng dụng, tối đa 90 ngày gần nhất
create or replace function public.thong_ke_truy_cap_ngay(so_ngay int default 14)
returns table (ngay date, ten_app text, so_luot bigint)
language sql
stable
security definer
set search_path = public
as $$
    select (t.thoi_gian at time zone 'Asia/Ho_Chi_Minh')::date as ngay,
           coalesce(t.ten_app, 'Khác')                         as ten_app,
           count(*)                                             as so_luot
    from public.thong_ke_truy_cap t
    where t.thoi_gian >= ((now() at time zone 'Asia/Ho_Chi_Minh')::date
                          - (least(greatest(so_ngay, 1), 90) - 1))::timestamp
                         at time zone 'Asia/Ho_Chi_Minh'
    group by 1, 2
    order by 1;
$$;

-- Tổng số lượt từ trước đến nay
create or replace function public.tong_luot_truy_cap()
returns bigint
language sql
stable
security definer
set search_path = public
as $$
    select count(*) from public.thong_ke_truy_cap;
$$;

revoke all on function public.thong_ke_truy_cap_ngay(int) from public;
revoke all on function public.tong_luot_truy_cap() from public;
grant execute on function public.thong_ke_truy_cap_ngay(int) to anon, authenticated;
grant execute on function public.tong_luot_truy_cap() to anon, authenticated;
