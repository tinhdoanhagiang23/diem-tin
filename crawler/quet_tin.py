"""
ĐIỂM TIN & LẮNG NGHE DƯ LUẬN — SCRIPT QUÉT TIN (chạy định kỳ trên GitHub Actions)

Mỗi lần chạy:
  1. Quét RSS cho 5 mục: Tiêu điểm 24h, Quốc tế, Dư luận MXH, Địa phương, Tuyên giáo TW
     (giữ nguyên cách lọc của bản Streamlit v5.7: chặn nguồn xấu, lọc đúng 124 xã/phường...).
  2. Ghi danh sách tin vào bảng Supabase `dt_bai`.
  3. Với tin mới: giải mã link Google News ra link báo gốc, tải bài và bóc nội dung
     (chế độ đọc) để trang web hiện ngay khi bấm vào tin.
  4. Xóa tin cũ hơn 30 ngày cho nhẹ cơ sở dữ liệu.

Biến môi trường cần có (đặt trong GitHub > Settings > Secrets and variables > Actions):
  SUPABASE_URL          vd: https://qqzsdxhqrdfvxnlurnyb.supabase.co
  SUPABASE_SERVICE_KEY  khóa service_role (KHÔNG phải anon key, KHÔNG đưa vào index.html)
"""

import base64
import calendar
import datetime as dt
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import feedparser
import requests
import trafilatura

# =====================================================================
# CẤU HÌNH
# =====================================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

SO_NGAY_LUU = 30          # xóa tin cũ hơn số ngày này
MAX_TRICH_XUAT = 150      # số bài tối đa bóc nội dung mỗi lần chạy
SO_LAN_THU_TOI_DA = 3     # bài bóc lỗi sẽ thử lại tối đa bấy nhiêu lần
SO_LUONG = 4              # số luồng tải bài song song

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

BLACKLIST = ["bbc", "rfa", "voa", "rfi", "việt tân", "viet tan", "luatkhoa", "thoibao", "nguoi-viet"]

LOCAL_KEYWORDS = [
    "tuyên quang", "hàm yên", "sơn dương", "chiêm hóa", "nà hang", "na hang", "lâm bình", "yên sơn",
    "hà giang 2", "tân trịnh", "thái hòa", "sơn thủy", "tát ngà", "an tường", "bắc mê", "bắc quang",
    "bạch đích", "bạch ngọc", "bạch xa", "bản máy", "bằng hành", "bằng lang", "bình an", "bình ca",
    "bình thuận", "bình xa", "cán tỷ", "cao bồ", "côn lôn", "đồng tâm", "đông thọ", "đồng văn",
    "đồng yên", "du già", "đường hồng", "đường thượng", "giáp trung", "hà giang 1", "hồ thầu",
    "hoàng su phì", "hồng sơn", "hồng thái", "hùng an", "hùng đức", "hùng lợi", "khâu vai",
    "khuôn lùng", "kiên đài", "kiến thiết", "hòa an", "kim bình", "lao chải", "liên hiệp", "linh hồ",
    "lực hành", "lũng cú", "lũng phìn", "lùng tám", "mậu duệ", "mèo vạc", "minh ngọc", "minh quang",
    "minh sơn", "minh tân", "minh thanh", "minh xuân", "mỹ lâm", "nấm dẩn", "nậm dịch", "nghĩa thuận",
    "ngọc đường", "ngọc long", "nhữ khê", "niêm sơn", "nông tiến", "pà vầy sủ", "phố bảng", "phú linh",
    "phú lương", "phù lưu", "pờ ly ngài", "quản bạ", "quang bình", "quảng nguyên", "sà phìn",
    "tùng bá", "sơn vĩ", "sủng máng", "tân an", "tân long", "tân mỹ", "tân quang", "tân thanh",
    "tân tiến", "tân trào", "thái bình", "thuận hòa", "thái sơn", "thắng mố", "thàng tín",
    "thanh thủy", "thông nguyên", "thượng lâm", "thượng nông", "thượng sơn", "tiên nguyên",
    "tiên yên", "tri phú", "trung hà", "trung sơn", "trung thịnh", "trường sinh", "tùng vài",
    "vị xuyên", "việt lâm", "vĩnh tuy", "xín mần", "xuân giang", "xuân vân", "yên cường", "yên hoa",
    "yên lập", "yên minh", "yên nguyên", "yên phú", "yên thành"
]

OFFICIAL_WARD_NAMES = [
    "Phường Mỹ Lâm", "Phường Minh Xuân", "Phường Nông Tiến", "Phường An Tường", "Phường Bình Thuận",
    "Phường Hà Giang 1", "Phường Hà Giang 2",
    "Xã Thượng Lâm", "Xã Lâm Bình", "Xã Minh Quang", "Xã Bình An", "Xã Côn Lôn", "Xã Yên Hoa",
    "Xã Thượng Nông", "Xã Hồng Thái", "Xã Nà Hang", "Xã Tân Mỹ", "Xã Yên Lập", "Xã Tân An",
    "Xã Chiêm Hóa", "Xã Hòa An", "Xã Kiên Đài", "Xã Tri Phú", "Xã Kim Bình", "Xã Yên Nguyên",
    "Xã Yên Phú", "Xã Bạch Xa", "Xã Phù Lưu", "Xã Hàm Yên", "Xã Bình Xa", "Xã Thái Sơn",
    "Xã Thái Hòa", "Xã Hùng Lợi", "Xã Trung Sơn", "Xã Thái Bình", "Xã Tân Long", "Xã Xuân Vân",
    "Xã Lực Hành", "Xã Yên Sơn", "Xã Nhữ Khê", "Xã Tân Trào", "Xã Minh Thanh", "Xã Sơn Dương",
    "Xã Bình Ca", "Xã Tân Thanh", "Xã Sơn Thủy", "Xã Phú Lương", "Xã Trường Sinh", "Xã Hồng Sơn",
    "Xã Đông Thọ",
    "Xã Lũng Cú", "Xã Đồng Văn", "Xã Sà Phìn", "Xã Phố Bảng", "Xã Lũng Phìn", "Xã Sủng Máng",
    "Xã Sơn Vĩ", "Xã Mèo Vạc", "Xã Khâu Vai", "Xã Niêm Sơn", "Xã Tát Ngà", "Xã Thắng Mố",
    "Xã Bạch Đích", "Xã Yên Minh", "Xã Mậu Duệ", "Xã Du Già", "Xã Đường Thượng", "Xã Lùng Tám",
    "Xã Cán Tỷ", "Xã Nghĩa Thuận", "Xã Quản Bạ", "Xã Tùng Vài", "Xã Yên Cường", "Xã Đường Hồng",
    "Xã Bắc Mê", "Xã Minh Ngọc", "Xã Ngọc Đường", "Xã Lao Chải", "Xã Thanh Thủy", "Xã Phú Linh",
    "Xã Linh Hồ", "Xã Bạch Ngọc", "Xã Vị Xuyên", "Xã Việt Lâm", "Xã Tân Quang", "Xã Đồng Tâm",
    "Xã Liên Hiệp", "Xã Bằng Hành", "Xã Bắc Quang", "Xã Hùng An", "Xã Vĩnh Tuy", "Xã Đồng Yên",
    "Xã Tiên Yên", "Xã Xuân Giang", "Xã Bằng Lang", "Xã Yên Thành", "Xã Quang Bình", "Xã Tân Trịnh",
    "Xã Thông Nguyên", "Xã Hồ Thầu", "Xã Nậm Dịch", "Xã Tân Tiến", "Xã Hoàng Su Phì", "Xã Thàng Tín",
    "Xã Bản Máy", "Xã Pờ Ly Ngài", "Xã Xín Mần", "Xã Pà Vầy Sủ", "Xã Nấm Dẩn", "Xã Trung Thịnh",
    "Xã Khuôn Lùng", "Xã Trung Hà", "Xã Kiến Thiết", "Xã Hùng Đức", "Xã Minh Sơn", "Xã Minh Tân",
    "Xã Thuận Hòa", "Xã Tùng Bá", "Xã Thượng Sơn", "Xã Cao Bồ", "Xã Ngọc Long", "Xã Giáp Trung",
    "Xã Tiên Nguyên", "Xã Quảng Nguyên",
]
OFFICIAL_WARD_NAMES_LOWER = [w.lower() for w in OFFICIAL_WARD_NAMES]

OTHER_PROVINCE_SIGNALS = [
    "hà nội", "hồ chí minh", "hải phòng", "đà nẵng", "huế", "lai châu", "điện biên", "sơn la",
    "lào cai", "cao bằng", "lạng sơn", "thái nguyên", "phú thọ", "bắc ninh", "quảng ninh",
    "ninh bình", "thanh hóa", "nghệ an", "hà tĩnh", "quảng trị", "quảng ngãi", "gia lai",
    "khánh hòa", "lâm đồng", "đắk lắk", "đồng nai", "tây ninh", "cần thơ", "vĩnh long",
    "đồng tháp", "cà mau", "an giang",
]

NEG_WORDS = ['bức xúc', 'sai phạm', 'kêu cứu', 'phản ánh', 'ô nhiễm', 'ngập', 'xuống cấp', 'chậm tiến độ',
             'đền bù', 'giải tỏa', 'tệ nạn', 'vi phạm', 'bất cập', 'chưa được', 'lừa đảo', 'chiếm đoạt',
             'bắt giữ', 'khởi tố']
POS_WORDS = ['biểu dương', 'khen thưởng', 'hoàn thành', 'vượt mức', 'xây dựng nông thôn mới', 'khang trang',
             'hiệu quả', 'ủng hộ', 'đóng góp', 'khắc phục', 'phát triển', 'thành công']


# =====================================================================
# HÀM TIỆN ÍCH (giữ logic bản v5.7)
# =====================================================================
def gnews_query_url(query, when="3d"):
    return f"https://news.google.com/rss/search?q={quote(query)}+when:{when}&hl=vi&gl=VN&ceid=VN:vi"


def build_ward_group_queries(group_size=10):
    skip = {"hà giang 1", "hà giang 2", "na hang"}
    wards = [w.title() for w in LOCAL_KEYWORDS if w not in skip]
    queries = []
    for i in range(0, len(wards), group_size):
        chunk = wards[i:i + group_size]
        queries.append("(" + " OR ".join(f'"{w}"' for w in chunk) + ")")
    return queries


def is_local_content(title, summary):
    content = (title + " " + summary).lower()
    if "tuyên quang" in content:
        return True
    if not any(name in content for name in OFFICIAL_WARD_NAMES_LOWER):
        return False
    return not any(p in content for p in OTHER_PROVINCE_SIGNALS)


def is_safe(title, link, summary):
    content = (title + " " + link + " " + summary).lower()
    return not any(bad in content for bad in BLACKLIST)


def clean_html(raw_html):
    if not raw_html:
        return ""
    return " ".join(re.sub(r"<.*?>", "", raw_html).split())


def analyze_sentiment(text):
    text = text.lower()
    neg = sum(1 for w in NEG_WORDS if w in text)
    pos = sum(1 for w in POS_WORDS if w in text)
    if neg > pos:
        return "Tiêu cực"
    if pos > neg:
        return "Tích cực"
    return "Trung lập"


def title_key(title):
    return re.sub(r"\W+", "", title.lower())[:80]


def make_khoa(title):
    return hashlib.sha1(title_key(title).encode("utf-8")).hexdigest()[:16]


# =====================================================================
# CẤU HÌNH 5 MỤC TIN
# =====================================================================
MUC = {
    "tieudiem": {
        "feeds": ["https://news.google.com/news/rss/headlines/section/topic/NATION?hl=vi&gl=VN&ceid=VN%3Avi"],
        "local": False, "cap": 50,
    },
    "quocte": {
        "feeds": ["https://www.vietnamplus.vn/rss/thegioi.rss"],
        "local": False, "cap": 50,
    },
    "mxh": {
        "feeds": [
            gnews_query_url('("facebook" OR "fanpage" OR "mạng xã hội" OR "tiktok") "Tuyên Quang"', when="2d"),
            gnews_query_url('("dư luận" OR "phản ánh" OR "bức xúc") "Tuyên Quang"', when="2d"),
            gnews_query_url('"Tuyên Quang"', when="1d"),
        ],
        "local": True, "cap": 80,
    },
    "diaphuong": {
        "feeds": [gnews_query_url('"Tuyên Quang"', when="14d")]
                 + [gnews_query_url(q, when="14d") for q in build_ward_group_queries(10)],
        "local": True, "cap": 200,
    },
    "tuyengiao": {
        "feeds": ["https://news.google.com/rss/search?q=(site:dangcongsan.vn+OR+site:tuyengiaodanvan.vn+OR+site:nhandan.vn)+(%22Ban+Tuy%C3%AAn+gi%C3%A1o%22+OR+%22D%C3%A2n+v%E1%BA%ADn%22)+when:3d&hl=vi&gl=VN&ceid=VN:vi"],
        "local": False, "cap": 50,
    },
}

http = requests.Session()
http.headers.update({"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.6"})


# =====================================================================
# BƯỚC 1: QUÉT RSS
# =====================================================================
def doc_rss(url):
    for lan in range(3):
        try:
            r = http.get(url, timeout=25)
            if r.status_code == 200:
                return feedparser.parse(r.content).entries
            print(f"  ! RSS {r.status_code}: {url[:90]}")
        except Exception as ex:
            print(f"  ! Lỗi RSS ({ex.__class__.__name__}): {url[:90]}")
        time.sleep(2 + lan * 3)
    return []


def tach_entry(e):
    """Chuẩn hóa 1 entry RSS -> dict. Bỏ đuôi ' - Tên báo' mà Google News gắn vào tiêu đề."""
    title = (e.get("title") or "").strip()
    link = e.get("link") or ""
    summary = clean_html(e.get("summary", ""))
    nguon = ""
    src = e.get("source")
    if src and isinstance(src, dict):
        nguon = (src.get("title") or "").strip()
    if nguon and title.endswith(" - " + nguon):
        title = title[: -len(" - " + nguon)].strip()
    if not nguon:
        m = re.match(r"https?://(?:www\.)?([^/]+)", link)
        nguon = m.group(1) if m and "news.google." not in m.group(1) else ""
    ts = None
    if e.get("published_parsed"):
        try:
            ts = dt.datetime.fromtimestamp(calendar.timegm(e["published_parsed"]), tz=dt.timezone.utc)
        except Exception:
            ts = None
    # tóm tắt RSS của Google News chỉ lặp lại tiêu đề -> bỏ
    if summary.startswith(title[:40]):
        summary = ""
    return {"title": title, "link": link, "summary": summary, "nguon": nguon, "ts": ts}


def quet_tat_ca():
    bai = {}  # khoa -> record
    for ma_muc, cfg in MUC.items():
        print(f"\n== Quét mục [{ma_muc}] ({len(cfg['feeds'])} nguồn)")
        seen, ds = set(), []
        for url in cfg["feeds"]:
            for e in doc_rss(url):
                it = tach_entry(e)
                if not it["title"] or not is_safe(it["title"], it["link"], it["summary"]):
                    continue
                k = title_key(it["title"])
                if not k or k in seen:
                    continue
                if cfg["local"] and not is_local_content(it["title"], it["summary"]):
                    continue
                seen.add(k)
                ds.append(it)
            if "news.google.com" in url:
                time.sleep(1.2)  # tránh bị Google chặn khi gọi dồn
        ds.sort(key=lambda x: x["ts"].timestamp() if x["ts"] else 0, reverse=True)
        ds = ds[: cfg["cap"]]
        print(f"   -> {len(ds)} tin")
        for it in ds:
            khoa = make_khoa(it["title"])
            if khoa not in bai:
                bai[khoa] = {**it, "khoa": khoa, "muc": set()}
            bai[khoa]["muc"].add(ma_muc)
    return bai


# =====================================================================
# SUPABASE (REST)
# =====================================================================
def sb_headers(extra=None):
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def sb_lay_ban_ghi(khoas):
    """Lấy các bản ghi đã có theo danh sách khóa."""
    co_san = {}
    khoas = list(khoas)
    for i in range(0, len(khoas), 100):
        chunk = khoas[i:i + 100]
        r = requests.get(
            f"{SUPABASE_URL}/rest/v1/dt_bai",
            params={"select": "khoa,muc,trang_thai,so_lan_thu,link_goc", "khoa": f"in.({','.join(chunk)})"},
            headers=sb_headers(), timeout=30)
        r.raise_for_status()
        for row in r.json():
            co_san[row["khoa"]] = row
    return co_san


def sb_upsert(rows):
    for i in range(0, len(rows), 200):
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/dt_bai", params={"on_conflict": "khoa"},
            headers=sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
            data=json.dumps(rows[i:i + 200], ensure_ascii=False).encode("utf-8"), timeout=60)
        if r.status_code >= 300:
            print("  ! Lỗi upsert:", r.status_code, r.text[:300])
            r.raise_for_status()


def sb_cap_nhat(khoa, data):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/dt_bai", params={"khoa": f"eq.{khoa}"},
        headers=sb_headers({"Prefer": "return=minimal"}),
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"), timeout=30)
    if r.status_code >= 300:
        print("  ! Lỗi cập nhật", khoa, r.status_code, r.text[:200])


def sb_xoa_tin_cu():
    moc = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=SO_NGAY_LUU)).isoformat()
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/dt_bai", params={"quet_luc": f"lt.{moc}"},
        headers=sb_headers({"Prefer": "return=minimal"}), timeout=30)
    print("Xóa tin cũ:", "OK" if r.status_code < 300 else f"lỗi {r.status_code} {r.text[:200]}")


# =====================================================================
# BƯỚC 3a: GIẢI MÃ LINK GOOGLE NEWS -> LINK BÁO GỐC
# =====================================================================
_khoa_google = threading.Lock()


def _giai_ma_base64_cu(gid):
    """Kiểu link cũ: link gốc nằm ngay trong chuỗi base64."""
    try:
        raw = base64.urlsafe_b64decode(gid + "=" * (-len(gid) % 4))
        m = re.search(rb"https?://[^\x00-\x20\x7f-\xff]+", raw)
        if m and b"AU_yqL" not in raw[:10]:
            return m.group(0).decode("ascii", "ignore")
    except Exception:
        pass
    return None


def _tach_ket_qua_batchexecute(text):
    """Phân tích phản hồi batchexecute của Google, trả về link gốc hoặc None."""
    try:
        phan = text.split("\n\n")[1]
        data = json.loads(phan)[:-2]
        return json.loads(data[0][2])[1]
    except Exception:
        m = re.search(r'\\"(https?://[^"\\]+)\\"', text)
        return m.group(1) if m else None


def giai_ma_google(url):
    m = re.search(r"news\.google\.com/(?:rss/)?(?:articles|read)/([A-Za-z0-9_\-]+)", url)
    if not m:
        return url
    gid = m.group(1)
    cu = _giai_ma_base64_cu(gid)
    if cu:
        return cu
    with _khoa_google:  # gọi tuần tự tới Google, tránh bị chặn
        try:
            r = http.get(f"https://news.google.com/rss/articles/{gid}", timeout=20)
            sig = re.search(r'data-n-a-sg="([^"]+)"', r.text)
            ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
            if not sig or not ts:
                r = http.get(f"https://news.google.com/articles/{gid}", timeout=20)
                sig = re.search(r'data-n-a-sg="([^"]+)"', r.text)
                ts = re.search(r'data-n-a-ts="([^"]+)"', r.text)
            if not sig or not ts:
                return None
            req = [
                "Fbv4je",
                f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],'
                f'"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{gid}",{ts.group(1)},"{sig.group(1)}"]',
            ]
            r2 = http.post(
                "https://news.google.com/_/DotsSplashUi/data/batchexecute",
                headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                data="f.req=" + quote(json.dumps([[req]])), timeout=20)
            return _tach_ket_qua_batchexecute(r2.text)
        except Exception as ex:
            print("  ! Giải mã Google lỗi:", ex.__class__.__name__)
            return None
        finally:
            time.sleep(0.6)


# =====================================================================
# BƯỚC 3b: TẢI BÀI & BÓC NỘI DUNG
# =====================================================================
def boc_noi_dung(link):
    r = http.get(link, timeout=25, allow_redirects=True)
    if r.status_code != 200:
        return None
    doc = trafilatura.bare_extraction(
        r.content, url=r.url, with_metadata=True, include_comments=False,
        include_tables=False, include_images=False, favor_precision=True)
    if doc is None:
        return None
    if not isinstance(doc, dict):
        doc = doc.as_dict()
    text = (doc.get("text") or "").strip()
    # trafilatura trả các đoạn cách nhau bởi 1 dòng mới -> đổi sang dòng trống cho dễ hiển thị
    doan = [d.strip() for d in text.split("\n") if d.strip()]
    return {
        "noi_dung": "\n\n".join(doan),
        "tom_tat": (doc.get("description") or "").strip(),
        "anh": doc.get("image") or None,
        "link_cuoi": r.url,
    }


def xu_ly_mot_bai(rec):
    khoa = rec["khoa"]
    link_goc = rec.get("link_goc")
    if not link_goc:
        link_goc = giai_ma_google(rec["link"]) if "news.google.com" in rec["link"] else rec["link"]
    cap_nhat = {"so_lan_thu": rec.get("so_lan_thu", 0) + 1}
    if not link_goc:
        cap_nhat["trang_thai"] = "loi"
        sb_cap_nhat(khoa, cap_nhat)
        return khoa, "không giải mã được link"
    cap_nhat["link_goc"] = link_goc
    try:
        kq = boc_noi_dung(link_goc)
    except Exception as ex:
        kq = None
        print("  ! Tải bài lỗi:", ex.__class__.__name__, link_goc[:80])
    if kq and len(kq["noi_dung"]) >= 200:
        cap_nhat.update({
            "noi_dung": kq["noi_dung"],
            "anh": kq["anh"],
            "trang_thai": "ok",
            "link_goc": kq["link_cuoi"] or link_goc,
        })
        if kq["tom_tat"]:
            cap_nhat["tom_tat"] = kq["tom_tat"][:600]
            cap_nhat["cam_xuc"] = analyze_sentiment(rec["title"] + " " + kq["tom_tat"])
        sb_cap_nhat(khoa, cap_nhat)
        return khoa, "ok"
    cap_nhat["trang_thai"] = "loi"
    if kq and kq["tom_tat"]:
        cap_nhat["tom_tat"] = kq["tom_tat"][:600]
    sb_cap_nhat(khoa, cap_nhat)
    return khoa, "không bóc được nội dung"


# =====================================================================
# CHẠY
# =====================================================================
def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        sys.exit("Thiếu SUPABASE_URL hoặc SUPABASE_SERVICE_KEY")

    t0 = time.time()
    bai = quet_tat_ca()
    print(f"\nTổng cộng {len(bai)} tin khác nhau.")
    if not bai:
        return

    co_san = sb_lay_ban_ghi(bai.keys())
    now = dt.datetime.now(dt.timezone.utc).isoformat()

    moi, cu = [], []
    for khoa, rec in bai.items():
        old = co_san.get(khoa)
        if old:
            muc = sorted(set(old.get("muc") or []) | rec["muc"])
            cu.append({"khoa": khoa, "tieu_de": rec["title"], "muc": muc, "quet_luc": now})
            rec["link_goc"] = old.get("link_goc")
            rec["trang_thai"] = old.get("trang_thai")
            rec["so_lan_thu"] = old.get("so_lan_thu") or 0
        else:
            moi.append({
                "khoa": khoa, "muc": sorted(rec["muc"]), "tieu_de": rec["title"], "nguon": rec["nguon"],
                "link_rss": rec["link"], "tom_tat": rec["summary"] or None,
                "cam_xuc": analyze_sentiment(rec["title"] + " " + rec["summary"]),
                "thoi_gian": rec["ts"].isoformat() if rec["ts"] else now,
                "quet_luc": now, "trang_thai": "cho", "so_lan_thu": 0,
            })
            rec["trang_thai"], rec["so_lan_thu"] = "cho", 0

    print(f"Tin mới: {len(moi)} · Tin đã có: {len(cu)}")
    if moi:
        sb_upsert(moi)
    if cu:
        sb_upsert(cu)

    # Bóc nội dung cho tin chưa có, ưu tiên tin mới nhất
    can_boc = [r for r in bai.values()
               if r["trang_thai"] in ("cho", "loi") and r["so_lan_thu"] < SO_LAN_THU_TOI_DA]
    can_boc.sort(key=lambda x: x["ts"].timestamp() if x["ts"] else 0, reverse=True)
    can_boc = can_boc[:MAX_TRICH_XUAT]
    print(f"\nBóc nội dung {len(can_boc)} bài...")
    dem = {"ok": 0, "loi": 0}
    with ThreadPoolExecutor(max_workers=SO_LUONG) as pool:
        for f in as_completed([pool.submit(xu_ly_mot_bai, r) for r in can_boc]):
            try:
                _, kq = f.result()
                dem["ok" if kq == "ok" else "loi"] += 1
            except Exception as ex:
                dem["loi"] += 1
                print("  ! Lỗi xử lý:", ex)
    print(f"   -> bóc được {dem['ok']}, lỗi {dem['loi']}")

    sb_xoa_tin_cu()
    print(f"\nXong sau {time.time() - t0:.0f} giây.")


if __name__ == "__main__":
    main()
