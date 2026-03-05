import streamlit as st
import pandas as pd
from datetime import datetime, date
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

st.set_page_config(page_title="Quản Lý Thu Mua Vật Tư", layout="wide", page_icon="📦")

# --- KẾT NỐI GOOGLE SHEETS BẰNG SECRETS ---
@st.cache_resource
def init_connection():
    # Kéo chìa khóa bảo mật từ Streamlit Cloud
    creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"], strict=False)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    # Kết nối vào file Trang tính
    sheet = client.open_by_url(st.secrets["SPREADSHEET_URL"])
    return sheet

try:
    db = init_connection()
    ws_trans = db.worksheet("Transactions")
    ws_mats = db.worksheet("Materials")
except Exception as e:
    st.error("❌ Không thể kết nối Google Sheets. Hãy kiểm tra lại file Secrets hoặc Quyền chia sẻ.")
    st.stop()

# --- HÀM ÉP SỐ ---
def clean_number(val):
    if pd.isna(val) or val == "": return 0.0
    if isinstance(val, list): val = val[0] if len(val) > 0 else 0.0
    val_str = str(val).replace(',', '').replace('₫', '').replace(' ', '')
    try: return float(val_str)
    except: return 0.0

st.title("📦 App Quản Lý Vật Tư (Bản Online)")
st.markdown("---")

tab1, tab2 = st.tabs(["📝 Nhập Hàng Mới", "📊 Lịch Sử Trực Tuyến"])

# ==========================================
# TAB 1: NHẬP ĐƠN HÀNG MỚI
# ==========================================
with tab1:
    st.subheader("1. Thông tin phiếu mua")
    col1, col2, col3 = st.columns(3)
    with col1:
        ngay = st.date_input("Ngày mua", date.today())
    with col2:
        loai = st.selectbox("Nguồn tiền", ["Công ty - Tiền túi", "Công ty - Tạm ứng", "Cá nhân"])
    with col3:
        trang_thai = "Chờ thanh toán" if "Tiền túi" in loai else "Đã hoàn tất"
        st.info(f"Trạng thái: **{trang_thai}**")

    st.subheader("2. Chi tiết vật tư")
    df_vattu = pd.DataFrame([{'Tên vật tư': "", 'Quy cách': "", 'Số lượng': 0.0, 'Đơn giá': 0.0, 'Nơi mua': "", 'Ghi chú': ""}])
    
    edited_df = st.data_editor(df_vattu, num_rows="dynamic", use_container_width=True,
        column_config={
            "Số lượng": st.column_config.NumberColumn("Số lượng", format="%f", min_value=0.0),
            "Đơn giá": st.column_config.NumberColumn("Đơn giá", format="%f", min_value=0.0),
        })

    if st.button("🚀 BẮN DỮ LIỆU LÊN GOOGLE SHEETS", type="primary", use_container_width=True):
        valid_data = edited_df[edited_df['Tên vật tư'].str.strip() != ""].copy()
        if not valid_data.empty:
            try:
                valid_data['Số lượng'] = valid_data['Số lượng'].apply(clean_number)
                valid_data['Đơn giá'] = valid_data['Đơn giá'].apply(clean_number)
                tong_tien = (valid_data['Số lượng'] * valid_data['Đơn giá']).sum()
                
                # Tạo Mã đơn hàng độc nhất theo giờ phút giây
                trans_id = datetime.now().strftime("MD%Y%m%d%H%M%S")
                
                # 1. Ghi lên sheet Transactions
                ws_trans.append_row([trans_id, ngay.strftime("%Y-%m-%d"), loai, tong_tien, trang_thai])
                
                # 2. Ghi lên sheet Materials
                mats_to_insert = []
                for index, row in valid_data.iterrows():
                    thanh_tien = row['Số lượng'] * row['Đơn giá']
                    mats_to_insert.append([
                        trans_id, str(row['Tên vật tư']), str(row['Quy cách']), 
                        row['Số lượng'], row['Đơn giá'], thanh_tien, 
                        str(row['Nơi mua']), str(row['Ghi chú'])
                    ])
                ws_mats.append_rows(mats_to_insert)
                
                st.success(f"🎉 Đã lưu Online thành công lên Google Sheets! (Mã đơn: {trans_id})")
            except Exception as e:
                st.error(f"❌ Có lỗi khi lưu: {e}")
        else:
            st.warning("⚠️ Bạn chưa nhập 'Tên vật tư'.")

# ==========================================
# TAB 2: LỊCH SỬ ONLINE TỪ GOOGLE SHEETS
# ==========================================
with tab2:
    st.subheader("🔍 Lấy dữ liệu trực tiếp từ máy chủ Google")
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        start_date = st.date_input("Từ ngày", date.today().replace(day=1))
    with f_col2:
        end_date = st.date_input("Đến ngày", date.today())
    
    st.write("---")
    if st.button("🔄 Tải Mới Dữ Liệu"):
        st.cache_resource.clear()
        st.rerun() # Giúp app tải lại mượt hơn
        
    try:
        trans_data = ws_trans.get_all_records()
        mats_data = ws_mats.get_all_records()
        
        if trans_data and mats_data:
            df_trans = pd.DataFrame(trans_data)
            df_mats = pd.DataFrame(mats_data)
            
            # Tự động tìm cột Ngày dù có dư khoảng trắng hay viết thường
            ngay_col = next((c for c in df_trans.columns if c.strip().lower() == 'ngày'), None)
            
            if ngay_col:
                df_trans[ngay_col] = pd.to_datetime(df_trans[ngay_col]).dt.date
                mask = (df_trans[ngay_col] >= start_date) & (df_trans[ngay_col] <= end_date)
                df_trans_filtered = df_trans.loc[mask]
            else:
                df_trans_filtered = df_trans
            
            if not df_trans_filtered.empty:
                df_view = pd.merge(df_mats, df_trans_filtered, on='Mã Đơn', how='inner')
                
                # Tự động tìm cột Thành tiền để tính tổng
                thanh_tien_col = next((c for c in df_view.columns if c.strip().lower() == 'thành tiền'), None)
                tong_chi = df_view[thanh_tien_col].sum() if thanh_tien_col else 0
                
                m1, m2 = st.columns(2)
                m1.metric(label="💰 TỔNG TIỀN ĐÃ CHI", value=f"{tong_chi:,.0f} ₫")
                m2.metric(label="📦 TỔNG SỐ MÓN", value=f"{len(df_view)} món")
                
                # Cấu hình tự động nhận diện định dạng cột số
                col_config = {}
                for c in df_view.columns:
                    c_lower = c.strip().lower()
                    if c_lower == 'số lượng':
                        col_config[c] = st.column_config.NumberColumn(format="%,.1f")
                    elif c_lower in ['đơn giá', 'thành tiền', 'tổng tiền']:
                        col_config[c] = st.column_config.NumberColumn(format="%,.0f ₫")
                
                # Lọc bỏ một số cột thừa thãi khi hiển thị nếu muốn
                cols_to_drop = [c for c in ['id', 'ID'] if c in df_view.columns]
                df_display = df_view.drop(columns=cols_to_drop)
                        
                st.dataframe(df_display, use_container_width=True, column_config=col_config)
            else:
                st.info("Không có giao dịch nào.")
        else:
            st.info("Trang tính đang trống.")
    except Exception as e:
        st.error(f"Lỗi tải dữ liệu: {e}")