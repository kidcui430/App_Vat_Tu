import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import re  
import time  

st.set_page_config(page_title="Quản Lý Thu Mua Vật Tư", layout="wide", page_icon="📦")

# ==========================================
# 🛑 HỆ THỐNG BẢO MẬT ĐĂNG NHẬP
# ==========================================
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"] 
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.markdown("### 🔐 HỆ THỐNG QUẢN LÝ NỘI BỘ")
        st.text_input("Vui lòng nhập mật khẩu để truy cập:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.markdown("### 🔐 HỆ THỐNG QUẢN LÝ NỘI BỘ")
        st.text_input("Vui lòng nhập mật khẩu để truy cập:", type="password", on_change=password_entered, key="password")
        st.error("❌ Mật khẩu không đúng. Vui lòng thử lại!")
        return False
    else:
        return True

if not check_password():
    st.stop()

# ==========================================
# 🚀 PHẦN MỀM CHÍNH 
# ==========================================
if 'form_key' not in st.session_state:
    st.session_state.form_key = 0

@st.cache_resource
def init_connection():
    creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS"], strict=False)
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(st.secrets["SPREADSHEET_URL"])
    return sheet

try:
    db = init_connection()
    ws_trans = db.worksheet("Transactions")
    ws_mats = db.worksheet("Materials")
    ws_incomes = db.worksheet("Incomes") # KẾT NỐI DATA NGUỒN THU MỚI
except Exception as e:
    st.error("❌ Không thể kết nối Google Sheets. Hãy kiểm tra lại file Secrets và chắc chắn đã tạo sheet 'Incomes'.")
    st.stop()

# --- HÀM ÉP SỐ CHỐNG LỖI 100% ---
def clean_number(val):
    if pd.isna(val) or str(val).strip() == "": return 0.0
    if isinstance(val, (int, float)): return float(val)
    
    val_str = str(val)
    val_str = re.sub(r'[^\d.,-]', '', val_str)
    if not val_str: return 0.0
    
    val_str = val_str.replace(',', '')
    if val_str.count('.') > 1:
        val_str = val_str.replace('.', '')
    elif val_str.count('.') == 1:
        if len(val_str.split('.')[-1]) == 3:
            val_str = val_str.replace('.', '')
            
    try: return float(val_str)
    except: return 0.0

st.title("📦 App THU VÀ CHI (TEST BY T)")
st.markdown("---")

# CHIA THÀNH 3 TAB ĐỂ QUẢN LÝ CHUYÊN NGHIỆP HƠN
tab1, tab2, tab3 = st.tabs(["📝 MUA VẬT TƯ", "💵 THU TIỀN", "📊 BẢNG TỔNG KẾT"])

# ==========================================
# --- TAB 1: NHẬP ĐƠN HÀNG MỚI (CHI) ---
# ==========================================
with tab1:
    st.subheader("1. Thông tin phiếu mua")
    col1, col2 = st.columns(2)
    with col1:
        ngay = st.date_input("Ngày mua", date.today())
    with col2:
        loai = st.selectbox("Hình thức thanh toán", ["Tiền mặt", "Chuyển khoản"])

    st.subheader("2. Chi tiết vật tư")
    df_vattu = pd.DataFrame([{'Tên vật tư': "", 'Quy cách': "Pcs", 'Số lượng': 0.0, 'Đơn giá': 0.0, 'Nơi mua': "", 'Ghi chú': ""}])
    
    edited_df = st.data_editor(
        df_vattu, num_rows="dynamic", use_container_width=True, key=f"editor_{st.session_state.form_key}",
        column_config={
            "Tên vật tư": st.column_config.TextColumn("Tên vật tư", required=True),
            "Quy cách": st.column_config.SelectboxColumn("Quy cách", options=["Pcs", "KG", "Con", "Cái", "Bộ", "Mét", "Lít", "Hộp", "Thùng", "Cuộn", "Tấm", "Ly", "Bao"], required=True),
            "Số lượng": st.column_config.NumberColumn("Số lượng", format="%,.1f", min_value=0.0),
            "Đơn giá": st.column_config.NumberColumn("Đơn giá", format="%,.0f", min_value=0.0),
        }
    )

    btn_col1, btn_col2 = st.columns([3, 1])
    with btn_col1:
        if st.button("🚀 LƯU ĐÃ MUA", type="primary", use_container_width=True):
            valid_data = edited_df[edited_df['Tên vật tư'].str.strip() != ""].copy()
            if not valid_data.empty:
                try:
                    valid_data['Số lượng'] = valid_data['Số lượng'].apply(clean_number)
                    valid_data['Đơn giá'] = valid_data['Đơn giá'].apply(clean_number)
                    tong_tien = (valid_data['Số lượng'] * valid_data['Đơn giá']).sum()
                    
                    now_vn = datetime.utcnow() + timedelta(hours=7)
                    trans_id = now_vn.strftime("TV%d%m%H%M%S") # TV = Tiền Vật tư (Chi)
                    ws_trans.append_row([trans_id, ngay.strftime("%Y-%m-%d"), loai, tong_tien])
                    
                    mats_to_insert = []
                    for index, row in valid_data.iterrows():
                        thanh_tien = row['Số lượng'] * row['Đơn giá']
                        mats_to_insert.append([
                            trans_id, str(row['Tên vật tư']), str(row['Quy cách']), 
                            row['Số lượng'], row['Đơn giá'], thanh_tien, str(row['Nơi mua']), str(row['Ghi chú'])
                        ])
                    ws_mats.append_rows(mats_to_insert)
                    
                    st.success(f"🎉 Đã lưu phiếu chi thành công! (Mã: {trans_id})")
                    time.sleep(1.5)
                    st.session_state.form_key += 1
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Có lỗi khi lưu: {e}")
            else:
                st.warning("⚠️ Bạn chưa nhập 'Tên vật tư'.")
                
    with btn_col2:
        if st.button("🔄 LÀM MỚI BẢNG", use_container_width=True, key="reset_tab1"):
            st.session_state.form_key += 1
            st.rerun()

# ==========================================
# --- TAB 2: NGUỒN THU (VÀO QUỸ) ---
# ==========================================
with tab2:
    st.subheader("💵 Cập nhật Nguồn Tiền Đầu Vào")
    
    with st.form("form_nhap_thu"):
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            ngay_thu = st.date_input("Ngày nhận tiền", date.today())
            nguon_thu = st.selectbox("Phân loại nguồn tiền", ["Nguồn tiền cá nhân", "Ứng từ Công ty", "Mượn bạn bè/người thân", "Nguồn thu khác"])
        with col_t2:
            # Tận dụng hàm ép số của bạn để cho phép user gõ 15.000.000 thoải mái không sợ lỗi
            so_tien_str = st.text_input("Số tiền nhận (VNĐ)", placeholder="Ví dụ: 15.000.000 hoặc 15000000")
            ghi_chu_thu = st.text_input("Ghi chú chi tiết (Không bắt buộc)")
            
        submit_thu = st.form_submit_button("💾 LƯU TIỀN THU", type="primary", use_container_width=True)
        
        if submit_thu:
            so_tien_thu = clean_number(so_tien_str)
            if so_tien_thu > 0:
                try:
                    now_vn = datetime.utcnow() + timedelta(hours=7)
                    # Tạo mã TT (Tiền Thu) để phân biệt với mã TV (Tiền Vật tư - Chi)
                    thu_id = now_vn.strftime("TT%d%m%H%M%S")
                    ws_incomes.append_row([thu_id, ngay_thu.strftime("%Y-%m-%d"), nguon_thu, so_tien_thu, ghi_chu_thu])
                    
                    st.success(f"🎉 Đã lưu nguồn thu thành công! +{so_tien_thu:,.0f} ₫ (Mã: {thu_id})")
                    time.sleep(1.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Có lỗi khi lưu nguồn thu: {e}")
            else:
                st.error("⚠️ Vui lòng nhập số tiền hợp lệ và lớn hơn 0.")

# ==========================================
# --- TAB 3: BẢNG THỐNG KÊ (THU CHI TỔNG HỢP) ---
# ==========================================
with tab2: # Giữ nguyên cấu trúc ẩn để code chạy độc lập tab, thực chất ở đây sửa thành "with tab3:"
    pass # Bỏ qua để viết đúng chuẩn tab3 bên dưới

with tab3:
    st.subheader("🔍 Phân tích dòng tiền trực tiếp từ máy chủ Google")
    f_col1, f_col2, f_col3 = st.columns([2, 2, 1])
    with f_col1:
        start_date = st.date_input("Từ ngày", date.today().replace(day=1))
    with f_col2:
        end_date = st.date_input("Đến ngày", date.today())
    with f_col3:
        st.write("") # Căn lót để nút bấm đều hàng với date input
        st.write("")
        if st.button("🔄 TẢI MỚI DỮ LIỆU", use_container_width=True):
            st.cache_resource.clear()
            st.rerun() 
    
    st.write("---")
    
    try:
        # Tải dữ liệu từ 3 sheets
        trans_data = ws_trans.get_all_records()
        mats_data = ws_mats.get_all_records()
        incomes_data = ws_incomes.get_all_records()
        
        # 1. XỬ LÝ DỮ LIỆU CHI (EXPENSES)
        tong_chi = 0
        df_view_chi = pd.DataFrame()
        if trans_data and mats_data:
            df_trans = pd.DataFrame(trans_data)
            df_mats = pd.DataFrame(mats_data)
            
            ngay_col = next((c for c in df_trans.columns if c.strip().lower() == 'ngày'), None)
            if ngay_col:
                df_trans[ngay_col] = pd.to_datetime(df_trans[ngay_col]).dt.date
                mask_chi = (df_trans[ngay_col] >= start_date) & (df_trans[ngay_col] <= end_date)
                df_trans_filtered = df_trans.loc[mask_chi]
            else:
                df_trans_filtered = df_trans
                
            if not df_trans_filtered.empty:
                df_view_chi = pd.merge(df_mats, df_trans_filtered, on='Mã Đơn', how='inner')
                for col in df_view_chi.columns:
                    if col.strip().lower() in ['số lượng', 'đơn giá', 'thành tiền', 'tổng tiền']:
                        df_view_chi[col] = df_view_chi[col].apply(clean_number)
                        
                tt_col = next((c for c in df_view_chi.columns if c.strip().lower() == 'thành tiền'), None)
                if tt_col:
                    tong_chi = df_view_chi[tt_col].sum()

        # 2. XỬ LÝ DỮ LIỆU THU (INCOMES)
        tong_thu = 0
        df_view_thu = pd.DataFrame()
        if incomes_data:
            df_incomes = pd.DataFrame(incomes_data)
            ngay_thu_col = next((c for c in df_incomes.columns if c.strip().lower() == 'ngày'), None)
            tien_thu_col = next((c for c in df_incomes.columns if c.strip().lower() == 'số tiền'), None)
            
            if ngay_thu_col and tien_thu_col:
                df_incomes[ngay_thu_col] = pd.to_datetime(df_incomes[ngay_thu_col]).dt.date
                mask_thu = (df_incomes[ngay_thu_col] >= start_date) & (df_incomes[ngay_thu_col] <= end_date)
                df_view_thu = df_incomes.loc[mask_thu].copy()
                
                if not df_view_thu.empty:
                    df_view_thu[tien_thu_col] = df_view_thu[tien_thu_col].apply(clean_number)
                    tong_thu = df_view_thu[tien_thu_col].sum()

        # 3. HIỂN THỊ METRICS (DASHBOARD TỔNG QUAN)
        ton_quy = tong_thu - tong_chi
        
        st.markdown("### 🧮 BẢNG TỔNG KẾT")
        m1, m2, m3 = st.columns(3)
        m1.metric(label="📈 TỔNG THU (Nguồn tiền vào)", value=f"{tong_thu:,.0f} ₫")
        m2.metric(label="📉 TỔNG CHI (Mua vật tư)", value=f"{tong_chi:,.0f} ₫")
        
        # Đổi màu hiển thị Tồn quỹ (Xanh nếu còn tiền, Đỏ nếu âm quỹ)
        if ton_quy >= 0:
            m3.metric(label="💰 TỒN QUỸ HIỆN TẠI", value=f"{ton_quy:,.0f} ₫", delta="Dương quỹ")
        else:
            m3.metric(label="🚨 TỒN QUỸ HIỆN TẠI", value=f"{ton_quy:,.0f} ₫", delta="- Âm quỹ (Cần bù thêm)", delta_color="inverse")

        st.write("---")
        
        # 4. BẢNG HIỂN THỊ CHI TIẾT DƯỚI DẠNG TAB CON
        sub_tab1, sub_tab2 = st.tabs(["📝 Lịch sử Chi Tiền", "💵 Lịch sử Thu Tiền"])
        
        with sub_tab1:
            if not df_view_chi.empty:
                col_config_chi = {}
                for c in df_view_chi.columns:
                    c_lower = c.strip().lower()
                    if c_lower == 'số lượng': col_config_chi[c] = st.column_config.NumberColumn(format="%,.1f")
                    elif c_lower in ['đơn giá', 'thành tiền', 'tổng tiền']: col_config_chi[c] = st.column_config.NumberColumn(format="%,.0f ₫")
                
                cols_to_drop = [c for c in ['id', 'ID', 'Trạng thái', 'Trạng Thái'] if c in df_view_chi.columns]
                st.dataframe(df_view_chi.drop(columns=cols_to_drop), use_container_width=True, column_config=col_config_chi)
            else:
                st.info("Không có dữ liệu mua vật tư trong khoảng thời gian này.")
                
        with sub_tab2:
            if not df_view_thu.empty:
                col_config_thu = {}
                for c in df_view_thu.columns:
                    if c.strip().lower() == 'số tiền':
                        col_config_thu[c] = st.column_config.NumberColumn(format="%,.0f ₫")
                st.dataframe(df_view_thu, use_container_width=True, column_config=col_config_thu)
            else:
                st.info("Không có dữ liệu nguồn thu trong khoảng thời gian này.")

    except Exception as e:

        st.error(f"Lỗi tải hoặc tính toán dữ liệu: {e}")
