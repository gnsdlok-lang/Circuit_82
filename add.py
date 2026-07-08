import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials
import json
import hashlib 
from st_rsuite import date_picker
from datetime import date

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
# 1. 구글 스프레드시트 연결 및 유틸 함수
# ==========================================
@st.cache_resource
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

def make_hash(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ==========================================
# 2. 팝업(Dialog) UI 함수들
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
                    client = get_google_client()
                    account_sheet = client.open("수령 목록82").worksheet("계정관리")
                    cell = account_sheet.find(st.session_state['user_id'], in_column=2)
                    
                    if cell:
                        hashed_pw = make_hash(new_pw)
                        account_sheet.update_cell(cell.row, 3, hashed_pw)
                        st.success("변경 완료!")
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

@st.dialog("입고생성")
def dialog_create_request():
    st.subheader("새로운 입고 의뢰 작성")
    
    factory_list = ["기체공장", "기관공장", "부품공장", "제작공장", "성능공장"]
    selected_factory = st.selectbox("공장", factory_list)

    # 부서 목록 (기존 코드 유지)
    client = get_google_client()
    dept_sheet = client.open("수령 목록82").worksheet("부서")
    dept_data = dept_sheet.get_all_values()
    valid_depts = [row[1] for row in dept_data if len(row) > 1 and row[0] == selected_factory]
    if not valid_depts:
        valid_depts = ["부서 정보 없음"]
    selected_dept = st.selectbox("부서", valid_depts)

    item_name = st.text_input("품명")
    serial_num = st.text_input("일련번호")

    # ==========================================
    # 📆 요구일자 - st-rsuite 달력 사용
    # ==========================================
    st.markdown("**📆 요구일자**")
    
    req_date = date_picker(
        label="요구일자 선택",
        value=date.today(),
        key="req_date_picker",
        one_tap=True,           # 한 번 클릭으로 선택 가능하게
    )
    req_date_str = req_date.strftime("%Y-%m-%d")

    st.write("---")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("확인", use_container_width=True, type="primary"):
            if not item_name or not serial_num:
                st.warning("품명과 일련번호를 입력해주세요.")
            else:
                with st.spinner("기록 중..."):
                    # 기존 입고 생성 로직 그대로 사용
                    client = get_google_client()
                    board_sheet = client.open("수령 목록82").worksheet("상황판")
                    
                    row_count = len(board_sheet.col_values(1))
                    next_seq = row_count if row_count > 0 else 1
                    
                    req_datetime_str = f"{req_date_str} 13:00"
                    current_time_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                    
                    new_row = [
                        next_seq, selected_factory, selected_dept, item_name,
                        st.session_state['user_name'], serial_num, 1,
                        current_time_str, req_datetime_str, "", "", ""
                    ]
                    board_sheet.append_row(new_row)
                    st.success("입고 생성이 완료되었습니다.")
                    st.rerun()
    
    with col2:
        if st.button("뒤로가기", use_container_width=True):
            st.rerun()


@st.dialog("입고 확인")
def dialog_confirm_inbound(sheet_row_idx):
    st.write("정말 입고 처리하시겠습니까?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("확인", use_container_width=True, type="primary"):
            client = get_google_client()
            board_sheet = client.open("수령 목록82").worksheet("상황판")
            board_sheet.update_cell(sheet_row_idx, 7, 2) # 상태를 2로 변경
            st.success("입고 처리 완료!")
            st.rerun()
    with col2:
        if st.button("취소", use_container_width=True):
            st.rerun()

@st.dialog("수령 확인")
def dialog_confirm_receipt(sheet_row_idx):
    st.write("정말 완료수령 처리하시겠습니까?")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("확인", use_container_width=True, type="primary"):
            client = get_google_client()
            board_sheet = client.open("수령 목록82").worksheet("상황판")
            current_time_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            board_sheet.update_cell(sheet_row_idx, 7, 5)  # 상태를 5로 변경
            board_sheet.update_cell(sheet_row_idx, 12, current_time_str) # 12열 수령시간
            st.success("수령 처리 완료!")
            st.rerun()
    with col2:
        if st.button("취소", use_container_width=True):
            st.rerun()

@st.dialog("상태 확인")
def dialog_status_check(row_data, sheet_row_idx):
    st.markdown(f"**의뢰부서:** {row_data[1]} {row_data[2]}")
    st.markdown(f"**품명:** {row_data[3]}")
    st.markdown(f"**의뢰자:** {row_data[4]}")
    st.markdown(f"**일련번호:** {row_data[5]}")
    st.markdown(f"**입고일자:** {row_data[7]}")
    st.markdown(f"**요구일자:** {row_data[8]}")
    st.markdown(f"**작업시작:** {row_data[9] if len(row_data)>9 else '-'}")
    st.markdown(f"**작업종료:** {row_data[10] if len(row_data)>10 else '-'}")
    st.markdown(f"**수령일자:** {row_data[11] if len(row_data)>11 else '-'}")
    
    st.write("---")
    # 삭제 시 2차 확인을 위한 상태 변수
    if "confirm_delete" not in st.session_state:
        st.session_state.confirm_delete = False

    col1, col2 = st.columns(2)
    with col1:
        if row_data[6] == '1': # 상태가 1인 경우에만 삭제 가능
            if not st.session_state.confirm_delete:
                if st.button("삭제", use_container_width=True, type="primary"):
                    st.session_state.confirm_delete = True
                    st.rerun()
            else:
                st.warning("정말 삭제할까요?")
                if st.button("최종 삭제", use_container_width=True):
                    client = get_google_client()
                    board_sheet = client.open("수령 목록82").worksheet("상황판")
                    board_sheet.delete_rows(sheet_row_idx)
                    st.session_state.confirm_delete = False
                    st.success("삭제 완료")
                    st.rerun()
        else:
            if st.button("삭제", use_container_width=True, disabled=True):
                pass
            st.caption("※ 상태가 1일 때만 삭제 가능합니다.")
            
    with col2:
        if st.button("뒤로가기", use_container_width=True):
            st.session_state.confirm_delete = False
            st.rerun()

# ==========================================
# 3. 세션 상태 초기화
# ==========================================
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'login_attempts' not in st.session_state: st.session_state['login_attempts'] = 0 
if 'lockout_until' not in st.session_state: st.session_state['lockout_until'] = None 
if 'page' not in st.session_state: st.session_state['page'] = 'login' 

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
                with st.spinner('확인 중...'):
                    try:
                        client = get_google_client()
                        account_sheet = client.open("수령 목록82").worksheet("계정관리")
                        data = account_sheet.get_all_values()
                        
                        login_success = False
                        for row in data[1:]:
                            # 올바른 인덱스 적용: B열(1), C열(2), D열(3), E열(4)
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
# 화면 분기 처리 (로그인 이후)
# ==========================================
else:
    # ------------------------------------------------
    # [화면 2] 메인 화면
    # ------------------------------------------------
    if st.session_state['page'] == 'main':
        level_str = "일반"
        if st.session_state['user_level'] == "2": level_str = "VIP"
        elif st.session_state['user_level'] == "3": level_str = "관리자"
            
        st.markdown(f"**{st.session_state['user_name']}**님 환영합니다! *(권한: {level_str})*")
        st.write("---")
        
        # 버튼 배치 (관리자/일반사용자)
        if st.session_state['user_level'] == "3":
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("입고/수령하기\n(의뢰자)", use_container_width=True):
                    st.session_state['page'] = 'inbound_outbound'
                    st.rerun()
            with col2:
                st.button("작업 시작/종료\n(작업자)", use_container_width=True) # 기능 추후 추가
            with col3:
                st.button("관리자 화면", use_container_width=True) # 기능 추후 추가
        else:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("입고/수령하기\n(의뢰자)", use_container_width=True):
                    st.session_state['page'] = 'inbound_outbound'
                    st.rerun()
            with col2:
                st.button("작업 시작/종료\n(작업자)", use_container_width=True)
                
        st.write("")
        st.write("")
        st.button("로그아웃", on_click=lambda: st.session_state.clear(), use_container_width=True)
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        # 비밀번호 변경 (어두운 회색 스타일 연출)
        st.markdown(
            """<style>div.stButton > button:first-child { border:none; background:transparent; color:#666666; box-shadow:none; }</style>""", 
            unsafe_allow_html=True
        )
        if st.button("비밀번호 변경", use_container_width=True):
            st.session_state['page'] = 'change_pw'
            st.rerun()

    # ------------------------------------------------
    # [화면 3] 입고/수령 하기 (의뢰자)
    # ------------------------------------------------
    elif st.session_state['page'] == 'inbound_outbound':
        st.subheader("📦 입고/수령 상황판")
        
        client = get_google_client()
        board_sheet = client.open("수령 목록82").worksheet("상황판")
        raw_data = board_sheet.get_all_values()
        
        # 헤더가 있는 경우 처리
        if len(raw_data) > 1:
            # 원본 데이터 매핑용 (행 번호 계산을 위해)
            df = pd.DataFrame(raw_data[1:], columns=raw_data[0])
            df['sheet_row_idx'] = range(2, len(df) + 2) # 스프레드시트의 실제 행 번호 (헤더+1)
            
            # 최근 10개만 필터링
            df_display = df.tail(10).copy()
            
            # 화면에 보여줄 칼럼만 정리
            display_cols = df_display.iloc[:, [2, 3, 5, 6]] # 부서, 품명, 일련번호, 상태 (0-indexed)
            display_cols.columns = ["부서", "품명", "일련번호", "상태"]
            
            # DataFrame 표출 (라디오 단추 대신 행 자체를 터치하여 선택하게 만듦)
            event = st.dataframe(
                display_cols,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun"
            )
            
            selected_indices = event.selection.rows
        else:
            st.info("현재 등록된 데이터가 없습니다.")
            selected_indices = []
            df_display = None
            
        st.write("---")
        
        # 버튼 4개 배치
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            if st.button("입고생성", use_container_width=True):
                dialog_create_request()
                
        with c2:
            if st.button("입고", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    selected_row = df_display.iloc[selected_indices[0]]
                    if str(selected_row['상태']) == '1':
                        dialog_confirm_inbound(int(selected_row['sheet_row_idx']))
                    else:
                        st.error("다시 확인해주세요 (상태가 1이 아닙니다)")
                        
        with c3:
            if st.button("수령", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    selected_row = df_display.iloc[selected_indices[0]]
                    if str(selected_row['상태']) == '4':
                        dialog_confirm_receipt(int(selected_row['sheet_row_idx']))
                    else:
                        st.error("다시 확인해주세요 (상태가 4가 아닙니다)")
                        
        with c4:
            if st.button("상태확인", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    selected_row = df_display.iloc[selected_indices[0]]
                    idx_in_raw = int(selected_row['sheet_row_idx']) - 1 # 리스트 인덱스 (0-indexed, 헤더 포함)
                    dialog_status_check(raw_data[idx_in_raw], int(selected_row['sheet_row_idx']))

        st.write("")
        if st.button("⬅️ 메인으로 돌아가기", use_container_width=True):
            st.session_state['page'] = 'main'
            st.rerun()

    # ------------------------------------------------
    # [화면 4] 비밀번호 변경
    # ------------------------------------------------
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
