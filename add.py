import streamlit as st
from datetime import datetime

# 0. 모바일 화면에 최적화되도록 앱 페이지 설정
st.set_page_config(page_title="사내 수령 기록 시스템", page_icon="📦", layout="centered")

# 로그인 상태를 기억하기 위한 저장소(세션 상태) 초기화
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# ----------------------------------------------------
# 화면 1: 로그인 화면 (로그인이 안 되어 있을 때)
# ----------------------------------------------------
if not st.session_state['logged_in']:
    
    # 1. 상단 이미지/아이콘 자리 (나중에 이미지 파일로 교체 가능)
    # 이미지 파일이 준비되면 아래 주석(#)을 풀고 파일명을 적어주면 됩니다.
    # st.image("your_logo.png", width=120)
    st.markdown("<h3 style='text-align: center; color: #4A5568;'>🏢 사내 시스템</h3>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #718096; font-size: 14px;'>[여기에 추후 로고 아이콘 이미지가 들어갑니다]</p>", unsafe_allow_html=True)
    st.write("---") # 구분선
    
    # 2. 아이디, 비밀번호 입력 창
    user_id = st.text_input("아이디", placeholder="아이디를 입력하세요")
    user_pw = st.text_input("비밀번호", type="password", placeholder="비밀번호를 입력하세요")
    
    st.write("") # 공백 추가
    
    # 3. 로그인 버튼 (모바일 화면에 꽉 차도록 설정)
    if st.button("로그인", use_container_width=True, type="primary"):
        # 임시 테스트용 계정 (아이디: admin / 비밀번호: 1234)
        if user_id == "admin" and user_pw == "1234":
            st.session_state['logged_in'] = True
            st.rerun() # 화면을 새로고침하여 다음 화면으로 전환
        else:
            st.error("아이디 또는 비밀번호가 일치하지 않습니다.")
            
    # 4. 비밀번호 찾기 (작은 글씨로 하단에 배치)
    st.markdown(
        "<div style='text-align: center; margin-top: 15px;'>"
        "<a href='#' style='font-size: 12px; color: #A0AEC0; text-decoration: none;'>비밀번호 찾기</a>"
        "</div>", 
        unsafe_allow_html=True
    )

# ----------------------------------------------------
# 화면 2: 메인 화면 (로그인이 성공했을 때)
# ----------------------------------------------------
else:
    st.title("📦 물품 수령 처리")
    st.write(f"접속 계정: **{st.session_state.get('user_id', '임시 관리자')}**")
    st.write("---")
    
    # 큰 여백 주기
    st.write("")
    st.write("")
    
    # 1. 수령처리 버튼 (눈에 띄는 파란색/초록색 계열 버튼)
    if st.button("📢 수령 처리하기", use_container_width=True):
        # 버튼을 누른 현재 시간을 초 단위까지 기록
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        st.success(f"수령 처리가 완료되었습니다!")
        st.info(f"⏰ 기록된 시간: {current_time}")
        st.caption("※ 지금은 화면에 시간만 뜨지만, 다음 단계에서 이 시간이 구글 스프레드시트에 자동으로 저장됩니다.")
        
    # 여백 주기
    st.write("")
    st.write("")
    st.write("")
    
    # 2. 나가기(로그아웃) 버튼
    if st.button("🚪 시스템 나가기", use_container_width=True):
        st.session_state['logged_in'] = False
        st.rerun() # 화면을 새로고침하여 로그인 화면으로 복귀