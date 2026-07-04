import streamlit as st
from datetime import datetime, timedelta, timezone
import gspread
from google.oauth2.service_account import Credentials
import json
import hashlib 

KST = timezone(timedelta(hours=9))

# 0. 앱 페이지 기본 설정 및 디자인 숨기기
st.set_page_config(page_title="사내 수령 기록 시스템", page_icon="📦", layout="centered")

hide_streamlit_style = """
<style>
header {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# 1. 구글 스프레드시트 연결 및 해시 함수
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

# [추가됨] 팝업창(Dialog) UI 함수
@st.dialog("비밀번호 최종 확인")
def confirm_password_change(new_pw):
    st.write("정말 비밀번호를 변경하시겠습니까?")
    st.caption("변경 시 자동으로 로그아웃되며, 새로운 비밀번호로 다시 로그인해야 합니다.")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("최종 변경", use_container_width=True, type="primary"):
            with st.spinner("구글 시트에 업데이트 중입니다..."):
                try:
                    client = get_google_client()
                    account_sheet = client.open("수령 목록82").worksheet("계정관리")
                    
                    # 1. B열(2번째 열)에서 현재 로그인한 아이디의 위치(Cell)를 찾습니다.
                    cell = account_sheet.find(st.session_state['user_id'], in_column=2)
                    
                    if cell:
                        # 2. 찾은 행(Row)의 C열(3번째 열)을 새로운 비밀번호의 해시값으로 바꿉니다.
                        hashed_pw = make_hash(new_pw)
                        account_sheet.update_cell(cell.row, 3, hashed_pw)
                        
                        st.success("변경 완료!")
                        # 모든 로그인 정보 초기화 후 첫 화면으로 쫓아내기
                        for key in list(st.session_state.keys()):
                            del st.session_state[key]
                        st.session_state['logged_in'] = False
                        st.rerun()
                    else:
                        st.error("계정을 찾을 수 없어 변경에 실패했습니다.")
                except Exception as e:
                    st.error(f"업데이트 중 에러 발생: {e}")
    
    with col2:
        if st.button("취소", use_container_width=True):
            st.rerun() # 팝업창 닫기

# 2. 보안, 로그인 상태 및 화면 상태 세션 초기화
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'login_attempts' not in st.session_state:
    st.session_state['login_attempts'] = 0 
if 'lockout_until' not in st.session_state:
    st.session_state['lockout_until'] = None 
if 'page' not in st.session_state:
    st.session_state['page'] = 'main' # 화면 이동을 위한 이정표 생성

# ----------------------------------------------------
# 화면 1: 로그인 화면 
# ----------------------------------------------------
if not st.session_state['logged_in']:
    st.markdown("<h3 style='text-align: center; color: #4A5568;'>🏢 사내 시스템</h3>", unsafe_allow_html=True)
    st.write("---") 
    
    user_id = st.text_input("아이디", placeholder="아이디를 입력하세요")
    user_pw = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
    
    st.write("") 
    
    if st.button("로그인", use_container_width=True, type="primary"):
        if st.session_state['lockout_until'] and datetime.now(KST) < st.session_state['lockout_until']:
            remain_seconds = int((st.session_state['lockout_until'] - datetime.now(KST)).total_seconds())
            st.error(f"🚨 5회 연속 실패로 로그인이 차단되었습니다. {remain_seconds}초 후에 다시 시도해 주세요.")
        else:
            if st.session_state['lockout_until'] and datetime.now(KST) >= st.session_state['lockout_until']:
                st.session_state['login_attempts'] = 0
                st.session_state['lockout_until'] = None
            
            if user_id and user_pw:
                with st.spinner('계정 정보를 확인 중입니다...'):
                    try:
                        client = get_google_client()
                        account_sheet = client.open("수령 목록82").worksheet("계정관리")
                        data = account_sheet.get("B:E")
                        
                        login_success = False
                        
                        for row in data[1:]:
                            if len(row) >= 4:
                                hashed_input_pw = make_hash(user_pw)
                                if str(row[0]) == str(user_id) and str(row[1]) == str(hashed_input_pw):
                                    st.session_state['logged_in'] = True
                                    st.session_state['user_id'] = str(row[0])
                                    st.session_state['user_name'] = str(row[2])
                                    st.session_state['user_level'] = str(row[3])
                                    st.session_state['page'] = 'main' # 로그인 성공 시 메인 화면으로 설정
                                    login_success = True
                                    break 
                                    
                        if login_success:
                            st.session_state['login_attempts'] = 0
                            st.session_state['lockout_until'] = None
                            st.rerun() 
                        else:
                            st.session_state['login_attempts'] += 1
                            if st.session_state['login_attempts'] >= 5:
                                st.session_state['lockout_until'] = datetime.now(KST) + timedelta(minutes=3)
                                st.error("🚨 5회 연속 로그인 실패로 3분간 로그인이 차단됩니다.")
                            else:
                                st.error(f"아이디 또는 비밀번호가 일치하지 않습니다. (실패 횟수: {st.session_state['login_attempts']}/5)")
                            
                    except Exception as e:
                        st.error(f"구글 시트 연결 또는 데이터 확인 중 에러가 발생했습니다: {e}")
            else:
                st.warning("아이디와 비밀번호를 모두 입력해 주세요.")

# ----------------------------------------------------
# 화면 2 & 3: 로그인 성공 후 화면 분기점
# ----------------------------------------------------
else:
    # ------------------------------------------------
    # [화면 2] 메인 화면
    # ------------------------------------------------
    if st.session_state['page'] == 'main':
        st.title("📦 물품 수령 처리")
        
        level_str = "일반"
        if st.session_state['user_level'] == "2":
            level_str = "VIP"
        elif st.session_state['user_level'] == "3":
            level_str = "관리자"
            
        st.write(f"환영합니다, **{st.session_state['user_name']}**님! (권한: {level_str})")
        st.write("---")
        st.write("")
        
        if st.button("📢 수령 처리하기", use_container_width=True):
            current_time = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
            
            with st.spinner('구글 스프레드시트에 기록 중입니다...'):
                try:
                    client = get_google_client()
                    record_sheet = client.open("수령 목록82").worksheet("기록내용")
                    record_sheet.append_row([current_time, st.session_state['user_id']])
                    
                    st.success(f"{st.session_state['user_name']}님의 수령 처리가 완료되었습니다!")
                    st.info(f"⏰ 기록된 시간: {current_time}")
                    
                except Exception as e:
                    if "200" in str(e):
                        st.success(f"{st.session_state['user_name']}님의 수령 처리가 완료되었습니다!")
                        st.info(f"⏰ 기록된 시간: {current_time}")
                    else:
                        st.error(f"데이터 저장 중 진짜 문제가 발생했습니다: {e}")
            
        st.write("")
        st.write("")
        
        if st.button("🚪 시스템 나가기", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.session_state['logged_in'] = False
            st.rerun() 
            
        st.write("---")
        # [화면 2 아래쪽] 화면 3으로 넘어가는 작은 버튼
        if st.button("비밀번호 변경", use_container_width=True):
            st.session_state['page'] = 'change_pw'
            st.rerun()

    # ------------------------------------------------
    # [화면 3] 비밀번호 변경 화면
    # ------------------------------------------------
    elif st.session_state['page'] == 'change_pw':
        st.title("🔐 비밀번호 변경")
        st.write(f"접속 중인 아이디: **{st.session_state['user_id']}**")
        st.write("---")
        
        new_pw = st.text_input("재설정 비밀번호", type="password")
        new_pw_confirm = st.text_input("재설정 비밀번호 확인", type="password")
        
        st.write("")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("확인", use_container_width=True, type="primary"):
                # 예외 처리: 빈칸이거나 두 비밀번호가 다를 때
                if not new_pw or not new_pw_confirm:
                    st.warning("변경할 비밀번호를 입력해 주세요.")
                elif new_pw != new_pw_confirm:
                    st.error("입력하신 두 비밀번호가 다릅니다. 다시 확인해 주세요.")
                else:
                    # 모든 조건이 맞으면 팝업창 띄우기
                    confirm_password_change(new_pw)
        with col2:
            if st.button("취소", use_container_width=True):
                st.session_state['page'] = 'main' # 다시 화면 2로 돌아감
                st.rerun()
