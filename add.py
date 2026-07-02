import streamlit as st
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import json

# 0. 모바일 화면에 최적화되도록 앱 페이지 설정
# 기본 상/하단 디자인 숨기기 설정 포함
st.set_page_config(page_title="사내 수령 기록 시스템", page_icon="📦", layout="centered")

hide_streamlit_style = """
<style>
header {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# 로그인 상태를 기억하기 위한 저장소(세션 상태) 초기화
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# ----------------------------------------------------
# 화면 1: 로그인 화면 
# ----------------------------------------------------
if not st.session_state['logged_in']:
    st.markdown("<h3 style='text-align: center; color: #4A5568;'>🏢 사내 시스템</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #718096; font-size: 14px;'>[여기에 추후 로고 아이콘 이미지가 들어갑니다]</p>", unsafe_allow_html=True)
    st.write("---") 
    
    user_id = st.text_input("아이디", placeholder="아이디를 입력하세요")
    user_pw = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
    
    st.write("") 
    
    if st.button("로그인", use_container_width=True, type="primary"):
        if user_id == "admin" and user_pw == "1234":
            st.session_state['logged_in'] = True
            st.session_state['user_id'] = user_id # 로그인한 아이디 기억하기
            st.rerun() 
        else:
            st.error("아이디 또는 비밀번호가 일치하지 않습니다.")
            
    st.markdown(
        "<div style='text-align: center; margin-top: 15px;'>"
        "<a href='#' style='font-size: 12px; color: #A0AEC0; text-decoration: none;'>비밀번호 찾기</a>"
        "</div>", 
        unsafe_allow_html=True
    )

# ----------------------------------------------------
# 화면 2: 메인 화면 (수령 처리 및 구글 시트 전송)
# ----------------------------------------------------
else:
    st.title("📦 물품 수령 처리")
    st.write(f"접속 계정: **{st.session_state.get('user_id', '임시 관리자')}**")
    st.write("---")
    st.write("")
    st.write("")
    
    # [핵심 로직] 수령처리 버튼을 눌렀을 때
    if st.button("📢 수령 처리하기", use_container_width=True):
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_id = st.session_state.get('user_id')
        
        # 버튼을 누르면 '로딩 중' 표시를 띄우고 아래 작업 실행
        with st.spinner('구글 스프레드시트에 기록 중입니다...'):
            try:
                # 1. 스트림릿 비밀 금고(Secrets)에서 출입증 정보 가져오기
                key_dict = json.loads(st.secrets["gcp_service_account"])
                creds = Credentials.from_service_account_info(
                    key_dict,
                    scopes=[
                        "https://www.googleapis.com/auth/spreadsheets",
                        "https://www.googleapis.com/auth/drive"
                    ]
                )
                
                # 2. 구글 서비스에 권한 인증하고 접속하기
                client = gspread.authorize(creds)
                
                # 3. 내 구글 드라이브에 있는 시트 파일 열기 (이름이 일치해야 합니다!)
                sheet = client.open("수령기록부").sheet1
                
                # 4. 시트의 가장 아래쪽 빈 줄에 [시간, 아이디] 순서로 데이터 밀어넣기
                sheet.append_row([current_time, user_id])
                
                # 5. 성공 메시지 출력
                st.success(f"수령 처리가 완료되어 시트에 저장되었습니다!")
                st.info(f"⏰ 기록된 시간: {current_time}")
                
            except Exception as e:
                # 에러 발생 시 원인 출력 (예: 시트 이름 오타, 권한 부여 안됨 등)
                st.error(f"데이터 저장 중 문제가 발생했습니다: {e}")
        
    st.write("")
    st.write("")
    st.write("")
    
    if st.button("🚪 시스템 나가기", use_container_width=True):
        st.session_state['logged_in'] = False
        st.rerun()