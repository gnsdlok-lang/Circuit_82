import streamlit as st
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
import json

# 0. 앱 페이지 기본 설정 및 디자인 숨기기
st.set_page_config(page_title="사내 수령 기록 시스템", page_icon="📦", layout="centered")

hide_streamlit_style = """
<style>
header {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# 1. 구글 스프레드시트 연결 전용 함수
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

# 2. 보안 및 로그인 상태 세션 초기화
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'login_attempts' not in st.session_state:
    st.session_state['login_attempts'] = 0 # 로그인 실패 횟수
if 'lockout_until' not in st.session_state:
    st.session_state['lockout_until'] = None # 로그인 차단 해제 시간

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
        # [방어 로직 1] 현재 차단 상태인지 가장 먼저 확인
        if st.session_state['lockout_until'] and datetime.now() < st.session_state['lockout_until']:
            remain_seconds = int((st.session_state['lockout_until'] - datetime.now()).total_seconds())
            st.error(f"🚨 5회 연속 실패로 로그인이 차단되었습니다. {remain_seconds}초 후에 다시 시도해 주세요.")
        else:
            # 차단 시간이 지났으면 실패 횟수 초기화
            if st.session_state['lockout_until'] and datetime.now() >= st.session_state['lockout_until']:
                st.session_state['login_attempts'] = 0
                st.session_state['lockout_until'] = None
            
            if user_id and user_pw:
                with st.spinner('계정 정보를 확인 중입니다...'):
                    try:
                        client = get_google_client()
                        account_sheet = client.open("수령 목록82").worksheet("계정관리")
                        
                        # [최적화] 시트 전체가 아닌 B열(아이디) ~ E열(권한)까지만 지정해서 가져오기
                        # B~E열 데이터가 리스트 형태로 들어옵니다. [아이디, 암호, 이름, 권한]
                        data = account_sheet.get("B:E")
                        
                        login_success = False
                        
                        # 가져온 데이터 중 첫 줄(제목)을 제외하고 두 번째 줄(1번 인덱스)부터 반복 검사
                        for row in data[1:]:
                            # 데이터가 비어있는 빈 줄을 건너뛰기 위한 길이 체크
                            if len(row) >= 4:
                                # row[0]: 아이디, row[1]: 암호, row[2]: 이름, row[3]: 권한
                                if str(row[0]) == str(user_id) and str(row[1]) == str(user_pw):
                                    st.session_state['logged_in'] = True
                                    st.session_state['user_id'] = str(row[0])
                                    st.session_state['user_name'] = str(row[2])
                                    st.session_state['user_level'] = str(row[3])
                                    login_success = True
                                    break 
                                    
                        if login_success:
                            # 로그인 성공 시 실패 기록 초기화 및 화면 전환
                            st.session_state['login_attempts'] = 0
                            st.session_state['lockout_until'] = None
                            st.rerun() 
                        else:
                            # [방어 로직 2] 로그인 실패 처리 및 카운트 증가
                            st.session_state['login_attempts'] += 1
                            if st.session_state['login_attempts'] >= 5:
                                # 5회 실패 시 현재 시간부터 3분(180초) 동안 차단
                                st.session_state['lockout_until'] = datetime.now() + timedelta(minutes=3)
                                st.error("🚨 5회 연속 로그인 실패로 3분간 로그인이 차단됩니다.")
                            else:
                                st.error(f"아이디 또는 비밀번호가 일치하지 않습니다. (실패 횟수: {st.session_state['login_attempts']}/5)")
                            
                    except Exception as e:
                        st.error(f"구글 시트 연결 또는 데이터 확인 중 에러가 발생했습니다: {e}")
            else:
                st.warning("아이디와 비밀번호를 모두 입력해 주세요.")

# ----------------------------------------------------
# 화면 2: 메인 화면 (로그인 성공)
# ----------------------------------------------------
else:
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
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
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
        # 시스템을 나갈 때도 모든 정보를 안전하게 초기화
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.session_state['logged_in'] = False
        st.rerun()