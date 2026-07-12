import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import gspread
from gspread import Cell
from google.oauth2.service_account import Credentials
import json
import hashlib
import time
import uuid

KST = timezone(timedelta(hours=9))

# ==========================================
# 0. 앱 기본 설정
# ==========================================
st.set_page_config(page_title="사내 수령 기록 시스템", page_icon="📦", layout="centered")

hide_streamlit_style = """
<style>
header {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ==========================================
# 1. 구글 스프레드시트 연결 및 캐싱 함수
# ==========================================

# 1. API 연결: max_entries를 1로 제한하여 메모리 누수 방지
@st.cache_resource(show_spinner=False, max_entries=1)
def get_google_client():
    key_dict = json.loads(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(
        key_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    return gspread.authorize(creds)

# 2. 시트 열기: ID 기반으로 변경 (제공해주신 URL의 ID 적용)
@st.cache_resource(show_spinner=False, ttl=3600, max_entries=5)
def get_worksheet(sheet_name):
    client = get_google_client()
    # 제공해주신 시트 ID 적용 완료
    SHEET_KEY = "1yFIOdJBe4-cBQdGPPA8lRccaPuOqx0qR_YnA-4EHt8I"
    return client.open_by_key(SHEET_KEY).worksheet(sheet_name)

# 3. 데이터 캐싱: max_entries를 추가하여 동시에 여러 메모리가 점유되는 것을 방지
@st.cache_data(ttl=80, show_spinner=False, max_entries=1)
def get_cached_board_data():
    board_sheet = get_worksheet("상황판")
    return board_sheet.get_all_values()

@st.cache_data(ttl=1600, show_spinner=False, max_entries=1)
def get_cached_dept_data():
    dept_sheet = get_worksheet("부서")
    return dept_sheet.get_all_values()

def make_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_exact_row_idx(sheet, row_data, fallback_idx):
    if len(row_data) > 15 and str(row_data[15]).strip():
        uuid_str = str(row_data[15]).strip()
        try:
            cell = sheet.find(uuid_str, in_column=16)
            if cell:
                return cell.row
        except Exception:
            pass
    return fallback_idx
    
# ==========================================
# 2. Dialog 함수들
# ==========================================
@st.dialog("비밀번호 최종 확인")
def confirm_password_change(new_pw):
    st.write("정말 비밀번호를 변경하시겠습니까?")
    st.caption("변경 시 자동으로 로그아웃되며, 새로운 비밀번호로 다시 로그인해야 합니다.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("최종 변경", use_container_width=True, type="primary"):
            with st.spinner("업데이트 중..."):
                try:
                    account_sheet = get_worksheet("계정관리")
                    cell = account_sheet.find(st.session_state['user_id'], in_column=2)
                    
                    if cell:
                        hashed_pw = make_hash(new_pw)
                        account_sheet.update_cell(cell.row, 3, hashed_pw)
                        st.success("변경 완료! 다시 로그인해주세요.")
                        time.sleep(1.5) # 메시지 증발 방지
                        
                        for key in list(st.session_state.keys()):
                            del st.session_state[key]
                        st.session_state['logged_in'] = False
                        st.rerun()
                    else:
                        st.error("계정을 찾을 수 없습니다.")
                except Exception as e:
                    st.error(f"에러 발생: {e}")
    with col2:
        if st.button("취소", use_container_width=True):
            st.rerun()

@st.dialog("입고 확인")
def dialog_confirm_inbound(row_data, sheet_row_idx):
    st.write("정말 입고 처리하시겠습니까?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("확인", use_container_width=True, type="primary"):
            board_sheet = get_worksheet("상황판")
            row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
            
            # 동시성 재검증: 현재 상태가 '1(임시)'인지 확인
            current_status = board_sheet.cell(row_idx, 7).value
            if str(current_status).strip() == '1':
                board_sheet.update_cell(row_idx, 7, 2)
                get_cached_board_data.clear() 
                st.success("입고 처리 완료!")
                time.sleep(1) # 메시지 증발 방지
                st.rerun()
            else:
                st.error("⚠️ 이미 상태가 변경되었습니다. 새로고침됩니다.")
                time.sleep(1.5)
                get_cached_board_data.clear()
                st.rerun()
                
    with col2:
        if st.button("취소", use_container_width=True):
            st.rerun()

@st.dialog("수령 확인")
def dialog_confirm_receipt(row_data, sheet_row_idx):
    st.write("정말 완료수령 처리하시겠습니까?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("확인", use_container_width=True, type="primary"):
            board_sheet = get_worksheet("상황판")
            row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
            
            # 동시성 재검증: 현재 상태가 '4(수령대기)'인지 확인
            current_status = board_sheet.cell(row_idx, 7).value
            if str(current_status).strip() == '4':
                current_time_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                cells_to_update = [
                    Cell(row=row_idx, col=7, value=5),
                    Cell(row=row_idx, col=12, value=current_time_str),
                    Cell(row=row_idx, col=15, value=st.session_state.get('user_name', '알수없음'))
                ]
                board_sheet.update_cells(cells_to_update)
                get_cached_board_data.clear() 
                st.success("수령 처리 완료!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("⚠️ 이미 상태가 변경되었습니다. 새로고침됩니다.")
                time.sleep(1.5)
                get_cached_board_data.clear()
                st.rerun()
                
    with col2:
        if st.button("취소", use_container_width=True):
            st.rerun()

@st.dialog("상태 확인")
def dialog_status_check(row_data, sheet_row_idx):
    status_code = str(row_data[6]).strip() if len(row_data) > 6 else ""
    if st.session_state.get('page') == 'worker_dashboard':
        status_map = {'1': '⚪ 임시', '2': '🟡 작업대기', '3': '▶️ 작업중', '4': '🟢 작업완료', '5': '✅ 출고완료'}
    else:
        status_map = {'1': '⚪ 임시', '2': '🟡 입고', '3': '▶️ 작업중', '4': '🟢 수령대기', '5': '✅ 수령완료'}
    
    current_status = status_map.get(status_code, "알 수 없음")

    st.markdown(f"### 현재상태 : {current_status}")
    st.write("---")

    factory = row_data[1].strip() if len(row_data) > 1 else '-'
    dept = row_data[2].strip() if len(row_data) > 2 else '-'
    item = row_data[3].strip() if len(row_data) > 3 else '-'
    requester = row_data[4].strip() if len(row_data) > 4 else '-'
    serial = row_data[5].strip() if len(row_data) > 5 else '-'

    st.markdown("#### 📦 의뢰 정보")
    st.markdown(f"- **품명 (일련번호) :** {item} ({serial})")
    st.markdown(f"- **의뢰 부서 (의뢰자) :** {factory} {dept} ({requester})")
    st.write("")

    st.markdown("#### ⏱️ 타임라인")
    
    def trim_seconds(time_str):
        t = time_str.strip()
        if not t:
            return "-"
        if t.count(":") == 2:
            return t.rsplit(":", 1)[0]
        return t

    req_raw = row_data[8].strip() if len(row_data) > 8 and row_data[8].strip() else ""
    req_date = req_raw.split(" ")[0] if req_raw else "-"  
    
    inbound = trim_seconds(row_data[7]) if len(row_data) > 7 else "-"
    start_work = trim_seconds(row_data[9]) if len(row_data) > 9 else "-"
    end_work = trim_seconds(row_data[10]) if len(row_data) > 10 else "-"
    receipt = trim_seconds(row_data[11]) if len(row_data) > 11 else "-"

    c1, c2 = st.columns(2)
    c1.markdown(f"<span style='color:gray; font-size:14px'>요구일자</span><br>**{req_date}**", unsafe_allow_html=True)
    c2.markdown(f"<span style='color:gray; font-size:14px'>입고일자</span><br>**{inbound}**", unsafe_allow_html=True)
    st.write("") 

    c3, c4 = st.columns(2)
    c3.markdown(f"<span style='color:gray; font-size:14px'>작업시작</span><br>**{start_work}**", unsafe_allow_html=True)
    c4.markdown(f"<span style='color:gray; font-size:14px'>작업종료</span><br>**{end_work}**", unsafe_allow_html=True)
    st.write("") 

    c5, c6 = st.columns(2)
    c5.markdown(f"<span style='color:gray; font-size:14px'>수령일자</span><br>**{receipt}**", unsafe_allow_html=True)
    
    st.write("---")
    
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = False

    def set_delete():
        st.session_state.confirm_delete = True

    col1, col2 = st.columns(2)
    with col1:
        if len(row_data)>6 and str(row_data[6]).strip() == '1':
            if not st.session_state.confirm_delete:
                st.button("삭제", use_container_width=True, type="primary", on_click=set_delete)
            else:
                st.warning("정말 삭제할까요?")
                if st.button("최종 삭제", use_container_width=True):
                    board_sheet = get_worksheet("상황판")
                    row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
                    
                    # 동시성 검증
                    if str(board_sheet.cell(row_idx, 7).value).strip() == '1':
                        board_sheet.delete_rows(row_idx)
                        get_cached_board_data.clear() 
                        st.session_state.confirm_delete = False
                        st.success("삭제 완료")
                        time.sleep(1)
                        st.rerun() 
                    else:
                        st.error("⚠️ 이미 상태가 변경되어 삭제할 수 없습니다.")
                        time.sleep(1.5)
                        st.session_state.confirm_delete = False
                        st.rerun()
        else:
            st.button("삭제", use_container_width=True, disabled=True)
            st.caption("※ 상태가 (임시)일 때만 삭제 가능합니다.")
            
    with col2:
        if st.button("뒤로가기", use_container_width=True):
            st.session_state.confirm_delete = False
            st.rerun()

@st.dialog("작업 시작/종료 처리")
def dialog_worker_action(row_data, sheet_row_idx):
    st.markdown(f"**의뢰부서:** {row_data[1] if len(row_data)>1 else '-'} {row_data[2] if len(row_data)>2 else '-'}")
    st.markdown(f"**품명:** {row_data[3] if len(row_data)>3 else '-'}")
    st.markdown(f"**의뢰자:** {row_data[4] if len(row_data)>4 else '-'}")
    st.markdown(f"**일련번호:** {row_data[5] if len(row_data)>5 else '-'}")
    st.markdown(f"**입고일자:** {row_data[7] if len(row_data)>7 else '-'}")
    st.markdown(f"**요구일자:** {row_data[8] if len(row_data)>8 else '-'}")
    st.markdown(f"**작업시작:** {row_data[9] if len(row_data)>9 else '-'}")
    st.markdown(f"**작업종료:** {row_data[10] if len(row_data)>10 else '-'}")
    
    st.write("---")
    
    if "worker_confirm" not in st.session_state:
        st.session_state.worker_confirm = None

    def click_start():
        status = str(row_data[6]).strip() if len(row_data)>6 else ""
        start_time = str(row_data[9]).strip() if len(row_data)>9 else ""
        if status == '2' and start_time == "":
            st.session_state.worker_confirm = "start"
        else:
            st.session_state.worker_confirm = "error"

    def click_end():
        status = str(row_data[6]).strip() if len(row_data)>6 else ""
        end_time = str(row_data[10]).strip() if len(row_data)>10 else ""
        if status == '3' and end_time == "":
            st.session_state.worker_confirm = "end"
        else:
            st.session_state.worker_confirm = "error"

    def click_cancel():
        st.session_state.worker_confirm = None

    if st.session_state.worker_confirm == "start":
        st.warning("정말 작업을 시작하시겠습니까?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("최종 시작", use_container_width=True, type="primary"):
                board_sheet = get_worksheet("상황판")
                row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
                
                # 동시성 검증: '2(작업대기)' 상태인지 확인
                if str(board_sheet.cell(row_idx, 7).value).strip() == '2':
                    current_time_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                    cells = [
                        Cell(row=row_idx, col=7, value=3),
                        Cell(row=row_idx, col=10, value=current_time_str),
                        Cell(row=row_idx, col=13, value=st.session_state.get('user_name', '알수없음'))
                    ]
                    board_sheet.update_cells(cells) 
                    
                    get_cached_board_data.clear() 
                    st.session_state.worker_confirm = None
                    st.success("작업 시작 처리 완료!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("⚠️ 이미 다른 작업자가 상태를 변경했습니다.")
                    time.sleep(1.5)
                    st.session_state.worker_confirm = None
                    st.rerun()
        with c2:
            st.button("취소", use_container_width=True, on_click=click_cancel)
            
    elif st.session_state.worker_confirm == "end":
        st.warning("정말 작업을 종료하시겠습니까?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("최종 종료", use_container_width=True, type="primary"):
                board_sheet = get_worksheet("상황판")
                row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
                
                # 동시성 검증: '3(작업중)' 상태인지 확인
                if str(board_sheet.cell(row_idx, 7).value).strip() == '3':
                    current_time_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                    cells = [
                        Cell(row=row_idx, col=7, value=4),
                        Cell(row=row_idx, col=11, value=current_time_str),
                        Cell(row=row_idx, col=14, value=st.session_state.get('user_name', '알수없음'))
                    ]
                    board_sheet.update_cells(cells)
                    
                    get_cached_board_data.clear() 
                    st.session_state.worker_confirm = None
                    st.success("작업 종료 처리 완료!")
                    time.sleep(1)
                    st.rerun() 
                else:
                    st.error("⚠️ 이미 다른 작업자가 상태를 변경했습니다.")
                    time.sleep(1.5)
                    st.session_state.worker_confirm = None
                    st.rerun()
        with c2:
            st.button("취소", use_container_width=True, on_click=click_cancel)
            
    elif st.session_state.worker_confirm == "error":
        st.error("상태를 확인해주세요. (현재 상태에선 시작/종료할 수 없습니다)")
        st.button("돌아가기", use_container_width=True, on_click=click_cancel)

    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.button("시작", use_container_width=True, type="primary", on_click=click_start)
        with col2:
            st.button("종료", use_container_width=True, type="primary", on_click=click_end)
        with col3:
            if st.button("뒤로가기", use_container_width=True):
                st.session_state.worker_confirm = None
                st.rerun()

# ==========================================
# 3. 세션 상태 초기화
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'login_attempts' not in st.session_state:
    st.session_state['login_attempts'] = 0
if 'lockout_until' not in st.session_state:
    st.session_state['lockout_until'] = None
if 'page' not in st.session_state:
    st.session_state['page'] = 'login'

# ==========================================
# 화면 1: 로그인 화면
# ==========================================
if not st.session_state['logged_in']:
    st.markdown("<h3 style='text-align: center; color: #4A5568;'>🏢 사내 시스템</h3>", unsafe_allow_html=True)
    st.write("---")
    
    user_id = st.text_input("아이디", placeholder="아이디를 입력하세요")
    user_pw = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
    
    if st.button("로그인", use_container_width=True, type="primary"):
        if st.session_state['lockout_until'] and datetime.now(KST) < st.session_state['lockout_until']:
            remain = int((st.session_state['lockout_until'] - datetime.now(KST)).total_seconds())
            st.error(f"🚨 5회 실패. {remain}초 후 시도해주세요.")
        else:
            if st.session_state['lockout_until'] and datetime.now(KST) >= st.session_state['lockout_until']:
                st.session_state['login_attempts'] = 0
                st.session_state['lockout_until'] = None
            
            if user_id and user_pw:
                with st.spinner('로그인 중... (데이터 동기화)'):
                    try:
                        account_sheet = get_worksheet("계정관리")
                        data = account_sheet.get_all_values()
                        
                        login_success = False
                        for row in data[1:]:
                            if len(row) >= 4:
                                hashed_input_pw = make_hash(user_pw)
                                if str(row[1]) == str(user_id) and str(row[2]) == str(hashed_input_pw):
                                    st.session_state['logged_in'] = True
                                    st.session_state['user_id'] = str(row[1])
                                    st.session_state['user_name'] = str(row[3])
                                    st.session_state['user_level'] = str(row[4])
                                    st.session_state['page'] = 'main'
                                    login_success = True
                                    break
                                    
                        if login_success:
                            st.session_state['login_attempts'] = 0
                            get_cached_board_data()
                            get_cached_dept_data()
                            st.rerun()
                        else:
                            st.session_state['login_attempts'] += 1
                            if st.session_state['login_attempts'] >= 5:
                                st.session_state['lockout_until'] = datetime.now(KST) + timedelta(minutes=3)
                                st.error("🚨 5회 연속 실패. 3분간 차단됩니다.")
                            else:
                                st.error(f"정보 불일치 ({st.session_state['login_attempts']}/5)")
                    except Exception as e:
                        st.error(f"에러 발생: {e}")
            else:
                st.warning("아이디와 비밀번호를 모두 입력해 주세요.")

# ==========================================
# 로그인 이후 화면 분기
# ==========================================
else:
    # ------------------ 메인 메뉴 ------------------
    if st.session_state['page'] == 'main':
        level_str = "일반"
        if st.session_state['user_level'] == "2":
            level_str = "VIP"
        elif st.session_state['user_level'] == "3":
            level_str = "관리자"
            
        st.markdown(f"### 👋 **{st.session_state['user_name']}**님, 환영합니다!")
        st.caption(f"현재 로그인된 계정 권한: **{level_str}**")
        st.write("---")
        
        st.markdown("#### 📌 원하시는 업무를 선택해주세요")
        st.write("") 
        
        if st.session_state['user_level'] == "3":
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("📦 입고/수령\n(의뢰자용)", use_container_width=True):
                    st.session_state['page'] = 'inbound_outbound'
                    st.rerun()
            with col2:
                if st.button("🛠️ 작업 시작/종료\n(작업자용)", use_container_width=True):
                    st.session_state['page'] = 'worker_dashboard'
                    st.rerun()
            with col3:
                st.button("⚙️ 관리자 화면\n(준비중)", use_container_width=True)
        else:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📦 입고/수령\n(의뢰자용)", use_container_width=True):
                    st.session_state['page'] = 'inbound_outbound'
                    st.rerun()
            with col2:
                if st.button("🛠️ 작업 시작/종료\n(작업자용)", use_container_width=True):
                    st.session_state['page'] = 'worker_dashboard'
                    st.rerun()
                
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.write("---")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔐 비밀번호 변경", use_container_width=True):
                st.session_state['page'] = 'change_pw'
                st.rerun()
        with c2:
            st.button("🚪 로그아웃", on_click=lambda: st.session_state.clear(), use_container_width=True)

    # ------------------ 입고/수령 상황판 (의뢰자용) ------------------
    elif st.session_state['page'] == 'inbound_outbound':
        st.subheader("📦 입고/수령 상황판")
        
        raw_data = get_cached_board_data()
        
        if len(raw_data) > 1:
            df = pd.DataFrame(raw_data[1:])
            df.columns = [str(i) for i in range(len(df.columns))]
            df['sheet_row_idx'] = df.index + 2  
            
            col_f1, col_f2 = st.columns([2.5, 1])
            with col_f1:
                search_query = st.text_input("🔍 품명, 부서, 일련번호 검색", "", key="search_inbound")
            with col_f2:
                st.write("") 
                st.write("")
                show_completed = st.checkbox("✅ 완료 포함", value=False, key="check_inbound")
                
            if '6' in df.columns:
                if not show_completed:
                    df = df[df['6'].astype(str).str.strip() != '5']
            
            if search_query:
                mask = False
                if '2' in df.columns: mask |= df['2'].astype(str).str.contains(search_query, case=False)
                if '3' in df.columns: mask |= df['3'].astype(str).str.contains(search_query, case=False)
                if '5' in df.columns: mask |= df['5'].astype(str).str.contains(search_query, case=False)
                df = df[mask]
                
            df = df.iloc[::-1]

            display_df = pd.DataFrame()
            display_df["부서"] = df['2'] if '2' in df.columns else ""
            display_df["품명"] = df['3'] if '3' in df.columns else ""
            display_df["일련번호"] = df['5'] if '5' in df.columns else ""
            
            status_map_inbound = {'1': '⚪ 임시', '2': '🟡 입고', '3': '▶️ 작업중', '4': '🟢 수령대기', '5': '✅ 수령완료'}
            if '6' in df.columns:
                display_df["상태"] = df['6'].astype(str).str.strip().map(status_map_inbound).fillna(df['6'])

            st.caption("※ 표의 가장 왼쪽 체크박스를 눌러 항목을 선택하세요.")
            st.caption("진행 순서 : ⚪ 임시 ➔ 🟡 입고 ➔ ▶️ 작업중 ➔ 🟢 수령대기 ➔ ✅ 수령완료")
            
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun"
            )
            selected_indices = event.selection.rows
        else:
            st.info("현재 등록된 데이터가 없습니다.")
            selected_indices = []
            df = pd.DataFrame()
            
        st.write("---")
        
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            if st.button("입고생성", use_container_width=True):
                st.session_state['page'] = 'create_inbound'
                st.rerun()

        with c2:
            if st.button("입고", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    
                    row_data = raw_data[sheet_row_idx - 1]
                    raw_status = str(row_data[6]).strip() if len(row_data)>6 else ""
                    
                    if raw_status == '1':
                        dialog_confirm_inbound(row_data, sheet_row_idx)
                    else:
                        st.error("상태가 (임시)가 아닙니다")

        with c3:
            if st.button("수령", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    
                    row_data = raw_data[sheet_row_idx - 1]
                    raw_status = str(row_data[6]).strip() if len(row_data)>6 else ""
                    
                    if raw_status == '4':
                        dialog_confirm_receipt(row_data, sheet_row_idx)
                    else:
                        st.error("상태가 (수령대기)가 아닙니다")

        with c4:
            if st.button("상태확인", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    
                    row_data = raw_data[sheet_row_idx - 1]
                    dialog_status_check(row_data, sheet_row_idx)

        st.write("")
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("🔄 새로고침", use_container_width=True):
                get_cached_board_data.clear()
                st.rerun()
        with col_btn2:
            if st.button("⬅️ 메인으로 돌아가기", use_container_width=True):
                st.session_state['page'] = 'main'
                st.rerun()

    # ------------------ 작업 시작/종료 (작업자용) ------------------
    elif st.session_state['page'] == 'worker_dashboard':
        st.subheader("🛠️ 작업 시작/종료 상황판")
        
        raw_data = get_cached_board_data()
        
        if len(raw_data) > 1:
            df = pd.DataFrame(raw_data[1:])
            df.columns = [str(i) for i in range(len(df.columns))]
            df['sheet_row_idx'] = df.index + 2 
            
            col_f1, col_f2 = st.columns([2.5, 1])
            with col_f1:
                search_query = st.text_input("🔍 품명, 부서, 일련번호 검색", "", key="search_worker")
            with col_f2:
                st.write("")
                st.write("")
                show_completed = st.checkbox("✅ 완료 포함", value=False, key="check_worker")
                
            if '6' in df.columns:
                if not show_completed:
                    df = df[~df['6'].astype(str).str.strip().isin(['1', '5'])]
            
            if search_query:
                mask = False
                if '2' in df.columns: mask |= df['2'].astype(str).str.contains(search_query, case=False)
                if '3' in df.columns: mask |= df['3'].astype(str).str.contains(search_query, case=False)
                if '5' in df.columns: mask |= df['5'].astype(str).str.contains(search_query, case=False)
                df = df[mask]
                
            df = df.iloc[::-1]

            display_df = pd.DataFrame()
            display_df["부서"] = df['2'] if '2' in df.columns else ""
            display_df["품명"] = df['3'] if '3' in df.columns else ""
            display_df["일련번호"] = df['5'] if '5' in df.columns else ""
            
            status_map_worker = {'1': '⚪ 임시', '2': '🟡 작업대기', '3': '▶️ 작업중', '4': '🟢 작업완료', '5': '✅ 출고완료'}
            if '6' in df.columns:
                display_df["상태"] = df['6'].astype(str).str.strip().map(status_map_worker).fillna(df['6'])

            st.caption("※ 표의 가장 왼쪽 체크박스를 눌러 항목을 선택하세요.")
            st.caption("진행 순서 : ⚪ 임시 ➔ 🟡 작업대기 ➔ ▶️ 작업중 ➔ 🟢 작업완료 ➔ ✅ 출고완료")
            
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun"
            )
            selected_indices = event.selection.rows
        else:
            st.info("현재 등록된 데이터가 없습니다.")
            selected_indices = []
            df = pd.DataFrame()
            
        st.write("---")
        
        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("시작/종료", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    
                    row_data = raw_data[sheet_row_idx - 1]
                    
                    st.session_state.worker_confirm = None
                    dialog_worker_action(row_data, sheet_row_idx)
        with c2:
            if st.button("상태확인", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    
                    row_data = raw_data[sheet_row_idx - 1]
                    
                    st.session_state.confirm_delete = False
                    dialog_status_check(row_data, sheet_row_idx)
        with c3:
            pass # 여백

        st.write("")
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("🔄 새로고침", use_container_width=True):
                get_cached_board_data.clear()
                st.rerun()
        with col_btn2:
            if st.button("⬅️ 메인으로 돌아가기", use_container_width=True):
                st.session_state['page'] = 'main'
                st.rerun()

    # ------------------ 새로운 입고 의뢰 작성 페이지 ------------------
    elif st.session_state['page'] == 'create_inbound':
        st.subheader("📝 새로운 입고 의뢰 작성")
        st.write("---")

        factory_list = ["기체공장", "기관공장", "부품공장", "제작공장", "성능공장"]
        selected_factory = st.selectbox("공장", factory_list, key="create_factory")

        try:
            dept_data = get_cached_dept_data()
            valid_depts = [row[1] for row in dept_data if len(row) > 1 and row[0] == selected_factory]
        except Exception as e:
            st.error(f"부서 로딩 실패: {e}")
            valid_depts = ["부서 정보 없음"]

        if not valid_depts:
            valid_depts = ["부서 정보 없음"]

        selected_dept = st.selectbox("부서", valid_depts, key="create_dept")

        item_name = st.text_input("품명", key="create_item", placeholder="품명을 입력하세요")
        serial_num = st.text_input("일련번호", key="create_serial", placeholder="일련번호를 입력하세요")

        st.write("")
        req_date = st.date_input("📆 요구일자 (클릭하여 선택)", value=None, format="YYYY/MM/DD")

        st.write("---")

        col1_btn, col2_btn = st.columns(2)
        with col1_btn:
            if st.button("확인", use_container_width=True, type="primary"):
                if not item_name.strip() or not serial_num.strip():
                    st.warning("품명과 일련번호를 입력해주세요.")
                elif req_date is None:
                    st.warning("요구일자를 달력에서 선택해주세요.")
                else:
                    with st.spinner("등록 중..."):
                        try:
                            board_sheet = get_worksheet("상황판")
                            row_count = len(board_sheet.col_values(1))
                            next_seq = row_count if row_count > 0 else 1

                            req_date_str = req_date.strftime("%Y-%m-%d")
                            req_datetime_str = f"{req_date_str} 13:00"
                            current_time_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

                            new_row = [
                                next_seq, selected_factory, selected_dept, item_name.strip(),
                                st.session_state.get('user_name', ''), serial_num.strip(), 1,
                                current_time_str, req_datetime_str, "", "", "", "", "", "",
                                str(uuid.uuid4())
                            ]
                            board_sheet.append_row(new_row)
                            
                            get_cached_board_data.clear() 
                            st.success("입고 생성 완료!")
                            time.sleep(1) # 메시지 증발 방지
                            
                            st.session_state['page'] = 'inbound_outbound'
                            st.rerun()
                        except Exception as e:
                            st.error(f"에러 발생: {e}")

        with col2_btn:
            if st.button("취소", use_container_width=True):
                st.session_state['page'] = 'inbound_outbound'
                st.rerun()

    # ------------------ 비밀번호 변경 화면 ------------------
    elif st.session_state['page'] == 'change_pw':
        st.title("🔐 비밀번호 변경")
        new_pw = st.text_input("재설정 비밀번호", type="password")
        new_pw_confirm = st.text_input("재설정 비밀번호 확인", type="password")
        
        st.write("")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("확인", use_container_width=True, type="primary"):
                if not new_pw or not new_pw_confirm:
                    st.warning("변경할 비밀번호를 입력해 주세요.")
                elif new_pw != new_pw_confirm:
                    st.error("두 비밀번호가 다릅니다.")
                else:
                    confirm_password_change(new_pw)
        with col2:
            if st.button("취소", use_container_width=True):
                st.session_state['page'] = 'main'
                st.rerun()
