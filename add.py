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
st.set_page_config(page_title="순회작업 기록 시스템", page_icon="📦", layout="centered")

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

@st.cache_resource(show_spinner=False, ttl=3600, max_entries=5)
def get_worksheet(sheet_name):
    client = get_google_client()
    SHEET_KEY = "1yFIOdJBe4-cBQdGPPA8lRccaPuOqx0qR_YnA-4EHt8I"
    return client.open_by_key(SHEET_KEY).worksheet(sheet_name)

@st.cache_data(ttl=80, show_spinner=False, max_entries=1)
def get_cached_board_data():
    board_sheet = get_worksheet("상황판")
    return board_sheet.get_all_values()

@st.cache_data(ttl=1600, show_spinner=False, max_entries=1)
def get_cached_dept_data():
    dept_sheet = get_worksheet("부서")
    return dept_sheet.get_all_values()

@st.cache_data(ttl=80, show_spinner=False, max_entries=1)
def get_cached_completed_data():
    completed_sheet = get_worksheet("완료기록")
    return completed_sheet.get_all_values()

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

# 워크데이 시간 계산 함수 (주말 제외)
def calc_workday_hours(start_str, end_str):
    if not start_str or not end_str: return 0.0
    try:
        t1 = datetime.strptime(start_str.strip(), "%Y-%m-%d %H:%M:%S")
        t2 = datetime.strptime(end_str.strip(), "%Y-%m-%d %H:%M:%S")
        if t1 > t2: return 0.0
        
        work_seconds = 0
        curr_time = t1
        # 1시간 단위로 스텝을 밟으며 주말(5: 토요일, 6: 일요일)을 제외하고 시간 누적
        while curr_time < t2:
            next_time = min(curr_time + timedelta(hours=1), t2)
            if curr_time.weekday() < 5:
                work_seconds += (next_time - curr_time).total_seconds()
            curr_time = next_time
            
        return work_seconds / 3600.0
    except:
        return 0.0

def format_hours(hours_float):
    if hours_float == 0.0: return "0시간"
    d = int(hours_float // 24)
    h = int(hours_float % 24)
    return f"{d}일 {h}시간" if d > 0 else f"{h}시간"
    
# ==========================================
# 2. Dialog 함수들
# ==========================================
@st.dialog("시스템 점검 설정")
def dialog_system_maintenance():
    account_sheet = get_worksheet("계정관리")
    # 계정관리 시트의 E1(1행 5열) 셀을 점검 상태 기록용으로 사용
    current_status = account_sheet.cell(1, 5).value 
    is_maintenance = (str(current_status).strip() == "MAINTENANCE")
    
    st.write(f"현재 상태: **{'🚨 점검 중' if is_maintenance else '🟢 정상 작동 중'}**")
    st.caption("시스템 점검을 시작하면 일반/VIP 권한 사용자의 로그인이 차단됩니다.")
    st.write("---")
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("점검 시작", use_container_width=True, disabled=is_maintenance, type="primary"):
            account_sheet.update_cell(1, 5, "MAINTENANCE")
            st.success("점검 모드가 켜졌습니다.")
            time.sleep(1)
            st.rerun()
    with c2:
        if st.button("점검 종료", use_container_width=True, disabled=not is_maintenance):
            account_sheet.update_cell(1, 5, "NORMAL")
            st.success("시스템이 정상화되었습니다.")
            time.sleep(1)
            st.rerun()

@st.dialog("완료기록 상세")
def dialog_completed_detail(row_data):
    st.markdown(f"**1. 공장/부서 :** {row_data[1] if len(row_data)>1 else '-'} / {row_data[2] if len(row_data)>2 else '-'}")
    st.markdown(f"**2. 품명/일련번호 :** {row_data[3] if len(row_data)>3 else '-'} / {row_data[5] if len(row_data)>5 else '-'}")
    st.markdown(f"**3. 요구일자 :** {row_data[8] if len(row_data)>8 else '-'}")
    st.markdown(f"**4. 입고일자 :** {row_data[7] if len(row_data)>7 else '-'} (의뢰자: {row_data[4] if len(row_data)>4 else '-'})")
    st.markdown(f"**5. 작업시작 :** {row_data[9] if len(row_data)>9 else '-'} (담당: {row_data[12] if len(row_data)>12 else '-'})")
    st.markdown(f"**6. 작업종료 :** {row_data[10] if len(row_data)>10 else '-'} (담당: {row_data[13] if len(row_data)>13 else '-'})")
    st.markdown(f"**7. 수령일자 :** {row_data[11] if len(row_data)>11 else '-'} (담당: {row_data[14] if len(row_data)>14 else '-'})")
    st.markdown(f"**8. 시작지연 :** {row_data[15] if len(row_data)>15 else '-'}")
    st.markdown(f"**9. 수령지연 :** {row_data[16] if len(row_data)>16 else '-'}")
    st.markdown(f"**10. 낭비시간 :** {row_data[17] if len(row_data)>17 else '-'}")
    
    if st.button("닫기", use_container_width=True):
        st.rerun()

@st.dialog("완료기록 삭제")
def dialog_delete_completed(row_data, sheet_row_idx):
    st.warning("정말 해당 행을 삭제하시겠습니까? (이 작업은 되돌릴 수 없습니다)")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("최종 삭제", use_container_width=True, type="primary"):
            completed_sheet = get_worksheet("완료기록")
            completed_sheet.delete_rows(sheet_row_idx)
            get_cached_completed_data.clear()
            st.success("행 삭제 완료!")
            time.sleep(1)
            st.rerun()
    with col2:
        if st.button("취소", use_container_width=True):
            st.rerun()

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
                        time.sleep(1.5)
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
            current_status = board_sheet.cell(row_idx, 7).value
            if str(current_status).strip() == '1':
                current_time_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
                # 5열: 의뢰자 기록, 7열: 상태 2로 변경, 8열: 입고일자 기록
                cells_to_update = [
                    Cell(row=row_idx, col=5, value=st.session_state.get('user_name', '알수없음')),
                    Cell(row=row_idx, col=7, value=2),
                    Cell(row=row_idx, col=8, value=current_time_str)
                ]
                board_sheet.update_cells(cells_to_update)
                get_cached_board_data.clear() 
                st.success("입고 처리 완료!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("⚠️ 이미 상태가 변경되었습니다.")
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
                st.error("⚠️ 이미 상태가 변경되었습니다.")
                time.sleep(1.5)
                get_cached_board_data.clear()
                st.rerun()
    with col2:
        if st.button("취소", use_container_width=True):
            st.rerun()

@st.dialog("입고/수령 취소")
def dialog_cancel_inbound_receipt(row_data, sheet_row_idx):
    st.write("취소할 작업을 선택해주세요.")
    status = str(row_data[6]).strip() if len(row_data) > 6 else ""

    col1, col2 = st.columns(2)
    with col1:
        if st.button("입고 취소", use_container_width=True, disabled=(status != '2'), type="primary"):
            board_sheet = get_worksheet("상황판")
            row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
            # 상태를 1로 변경, 5열(의뢰자)과 8열(입고일자) 데이터 삭제
            cells = [
                Cell(row=row_idx, col=7, value=1),
                Cell(row=row_idx, col=5, value=""),
                Cell(row=row_idx, col=8, value="")
            ]
            board_sheet.update_cells(cells)
            get_cached_board_data.clear()
            st.success("입고 취소 완료!")
            time.sleep(1)
            st.rerun()

    with col2:
        if st.button("수령 취소", use_container_width=True, disabled=(status != '5'), type="primary"):
            board_sheet = get_worksheet("상황판")
            row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
            # 상태를 4로 변경, 12열(수령일자)과 15열(수령 담당자) 데이터 삭제
            cells = [
                Cell(row=row_idx, col=7, value=4),
                Cell(row=row_idx, col=12, value=""),
                Cell(row=row_idx, col=15, value="")
            ]
            board_sheet.update_cells(cells)
            get_cached_board_data.clear()
            st.success("수령 취소 완료!")
            time.sleep(1)
            st.rerun()

    st.write("---")
    if st.button("닫기", use_container_width=True):
        st.rerun()

@st.dialog("시작/종료 취소")
def dialog_cancel_start_end(row_data, sheet_row_idx):
    st.write("취소할 작업을 선택해주세요.")
    status = str(row_data[6]).strip() if len(row_data) > 6 else ""

    col1, col2 = st.columns(2)
    with col1:
        if st.button("시작취소", use_container_width=True, disabled=(status != '3'), type="primary"):
            board_sheet = get_worksheet("상황판")
            row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
            # 상태를 2로 변경, 10열(작업시작시간), 13열(시작 담당자) 데이터 삭제
            cells = [
                Cell(row=row_idx, col=7, value=2),
                Cell(row=row_idx, col=10, value=""),
                Cell(row=row_idx, col=13, value="")
            ]
            board_sheet.update_cells(cells)
            get_cached_board_data.clear()
            st.success("작업 시작 취소 완료!")
            time.sleep(1)
            st.rerun()
    with col2:
        if st.button("종료취소", use_container_width=True, disabled=(status != '4'), type="primary"):
            board_sheet = get_worksheet("상황판")
            row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
            # 상태를 3으로 변경, 11열(작업종료시간), 14열(종료 담당자) 데이터 삭제
            cells = [
                Cell(row=row_idx, col=7, value=3),
                Cell(row=row_idx, col=11, value=""),
                Cell(row=row_idx, col=14, value="")
            ]
            board_sheet.update_cells(cells)
            get_cached_board_data.clear()
            st.success("작업 종료 취소 완료!")
            time.sleep(1)
            st.rerun()
            
    st.write("---")
    if st.button("닫기", use_container_width=True):
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
        if not t: return "-"
        if t.count(":") == 2: return t.rsplit(":", 1)[0]
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
    
    # VIP(권한 2)인 경우 닫기 버튼만 제공
    if st.session_state.get('user_level') == "2":
        if st.button("닫기", use_container_width=True):
            st.rerun()
    else:
        # 그 외 사용자는 삭제/뒤로가기 제공
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
                        
                        if str(board_sheet.cell(row_idx, 7).value).strip() == '1':
                            board_sheet.delete_rows(row_idx)
                            get_cached_board_data.clear() 
                            st.session_state.confirm_delete = False
                            st.success("삭제 완료")
                            time.sleep(1)
                            st.rerun() 
                        else:
                            st.error("⚠️ 이미 상태가 변경되어 삭제 불가")
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
        if status == '2' and start_time == "": st.session_state.worker_confirm = "start"
        else: st.session_state.worker_confirm = "error"

    def click_end():
        status = str(row_data[6]).strip() if len(row_data)>6 else ""
        end_time = str(row_data[10]).strip() if len(row_data)>10 else ""
        if status == '3' and end_time == "": st.session_state.worker_confirm = "end"
        else: st.session_state.worker_confirm = "error"

    def click_cancel():
        st.session_state.worker_confirm = None

    if st.session_state.worker_confirm == "start":
        st.warning("정말 작업을 시작하시겠습니까?")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("최종 시작", use_container_width=True, type="primary"):
                board_sheet = get_worksheet("상황판")
                row_idx = get_exact_row_idx(board_sheet, row_data, sheet_row_idx)
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
                    st.error("⚠️ 이미 상태가 변경되었습니다.")
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
                    st.error("⚠️ 이미 상태가 변경되었습니다.")
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
    st.markdown("<h3 style='text-align: center; color: #4A5568;'>🏢 순회작업 기록시스템</h3>", unsafe_allow_html=True)
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
                        
                        system_status = str(data[0][4]).strip() if len(data[0]) > 4 else ""
                        login_success = False
                        
                        for row in data[1:]:
                            if len(row) >= 4:
                                hashed_input_pw = make_hash(user_pw)
                                if str(row[1]) == str(user_id) and str(row[2]) == str(hashed_input_pw):
                                    user_level = str(row[4])
                                    
                                    # 시스템 점검 중일 경우 차단 (관리자 레벨 3 제외)
                                    if system_status == "MAINTENANCE" and user_level in ["1", "2"]:
                                        st.error("🚨 시스템이 현재 점검 중입니다. 잠시 후 다시 시도해주세요.")
                                        st.stop()
                                        
                                    st.session_state['logged_in'] = True
                                    st.session_state['user_id'] = str(row[1])
                                    st.session_state['user_name'] = str(row[3])
                                    st.session_state['user_level'] = user_level
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
        
        if st.session_state['user_level'] == "3": # 관리자
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
                if st.button("⚙️ 관리자 화면\n(관리자용)", use_container_width=True):
                    st.session_state['page'] = 'admin_dashboard'
                    st.rerun()
                    
        elif st.session_state['user_level'] == "2": # VIP
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📊 진행 상황판", use_container_width=True):
                    st.session_state['page'] = 'vip_dashboard'
                    st.rerun()
            with col2:
                if st.button("✅ 완료 확인", use_container_width=True):
                    st.session_state['page'] = 'vip_completed'
                    st.rerun()
                    
        else: # 일반 사용자
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

    # ------------------ 관리자 전용 대시보드 ------------------
    elif st.session_state['page'] == 'admin_dashboard':
        st.subheader("⚙️ 관리자 화면")
        st.write("---")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("완료 작업 확인", use_container_width=True):
                with st.spinner("데이터를 계산하고 이동 중입니다..."):
                    board_sheet = get_worksheet("상황판")
                    completed_sheet = get_worksheet("완료기록")
                    board_data = board_sheet.get_all_values()
                    
                    rows_to_delete = []
                    rows_to_append = []
                    
                    for i, row in enumerate(board_data):
                        if i == 0: continue
                        if len(row) > 6 and str(row[6]).strip() == '5': 
                            inbound_dt = row[7] if len(row) > 7 else "" 
                            start_dt = row[9] if len(row) > 9 else ""   
                            end_dt = row[10] if len(row) > 10 else ""   
                            receipt_dt = row[11] if len(row) > 11 else "" 
                            
                            start_delay = calc_workday_hours(inbound_dt, start_dt)
                            receipt_delay = calc_workday_hours(end_dt, receipt_dt)
                            waste_time = start_delay + receipt_delay
                            
                            while len(row) < 18:
                                row.append("")
                                
                            row[15] = format_hours(start_delay)   
                            row[16] = format_hours(receipt_delay) 
                            row[17] = format_hours(waste_time)    
                            
                            rows_to_append.append(row)
                            rows_to_delete.append(i + 1) 
                    
                    if rows_to_append:
                        completed_sheet.append_rows(rows_to_append)
                        for idx in sorted(rows_to_delete, reverse=True):
                            board_sheet.delete_rows(idx)
                        get_cached_board_data.clear()
                        get_cached_completed_data.clear()
                        
                st.session_state['page'] = 'admin_completed_tasks'
                st.rerun()

        with c2:
            if st.button("비밀번호 초기화", use_container_width=True):
                st.session_state['page'] = 'admin_pw_reset'
                st.rerun()
                
        with c3:
            if st.button("시스템 점검", use_container_width=True):
                dialog_system_maintenance()

        st.write("")
        st.write("---")
        if st.button("⬅️ 메인으로 돌아가기", use_container_width=True):
            st.session_state['page'] = 'main'
            st.rerun()

    # ------------------ 완료 작업 확인 (관리자 뷰어) ------------------
    elif st.session_state['page'] == 'admin_completed_tasks':
        st.subheader("✅ 완료 작업 기록")
        st.caption("※ 상황판에서 '완료' 처리된 작업들이 이곳으로 이동되며 지연 시간이 계산됩니다.")
        
        raw_completed = get_cached_completed_data()
        
        if len(raw_completed) > 1:
            df = pd.DataFrame(raw_completed[1:])
            df.columns = [str(i) for i in range(len(df.columns))]
            df['sheet_row_idx'] = df.index + 2
            
            display_df = pd.DataFrame()
            display_df["공장"] = df['1'] if '1' in df.columns else ""
            display_df["부서"] = df['2'] if '2' in df.columns else ""
            display_df["품명"] = df['3'] if '3' in df.columns else ""
            display_df["입고일자"] = df['7'] if '7' in df.columns else ""
            display_df["시작지연"] = df['15'] if '15' in df.columns else ""
            display_df["수령지연"] = df['16'] if '16' in df.columns else ""
            display_df["낭비시간"] = df['17'] if '17' in df.columns else ""
            
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun"
            )
            selected_indices = event.selection.rows
        else:
            st.info("현재 기록된 완료 데이터가 없습니다.")
            selected_indices = []
            df = pd.DataFrame()
            
        st.write("---")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("상세보기", use_container_width=True, type="primary"):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    row_data = raw_completed[sheet_row_idx - 1]
                    dialog_completed_detail(row_data)
        with c2:
            if st.button("행삭제", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    row_data = raw_completed[sheet_row_idx - 1]
                    dialog_delete_completed(row_data, sheet_row_idx)
        with c3:
            if st.button("뒤로가기", use_container_width=True):
                st.session_state['page'] = 'admin_dashboard'
                st.rerun()

    # ------------------ 비밀번호 초기화 페이지 ------------------
    elif st.session_state['page'] == 'admin_pw_reset':
        st.subheader("🔑 사용자 비밀번호 초기화")
        st.write("---")
        
        search_kw = st.text_input("검색 (아이디 또는 이름)", placeholder="최소 2글자 이상 입력하세요")
        
        if len(search_kw) >= 2:
            account_sheet = get_worksheet("계정관리")
            acc_data = account_sheet.get_all_values()
            
            matches = []
            for idx, row in enumerate(acc_data):
                if idx == 0: continue
                if len(row) > 3:
                    if search_kw in row[1] or search_kw in row[3]:
                        matches.append({"sheet_idx": idx + 1, "id": row[1], "name": row[3]})
            
            if matches:
                st.success(f"{len(matches)}명의 사용자가 검색되었습니다.")
                selected_user = st.radio(
                    "초기화할 사용자 선택",
                    options=matches,
                    format_func=lambda x: f"{x['name']} (ID: {x['id']})"
                )
                
                if st.button("선택 계정 초기화", type="primary"):
                    with st.spinner("초기화 진행 중..."):
                        new_hashed_pw = make_hash(selected_user['id'])
                        account_sheet.update_cell(selected_user['sheet_idx'], 3, new_hashed_pw)
                        st.success(f"{selected_user['name']}님의 비밀번호가 아이디와 동일하게 초기화되었습니다.")
            else:
                st.warning("검색 결과가 없습니다.")
        elif len(search_kw) == 1:
            st.warning("최소 2글자 이상 입력해주세요.")

        st.write("---")
        if st.button("뒤로가기"):
            st.session_state['page'] = 'admin_dashboard'
            st.rerun()

    # ------------------ VIP 전용 : 진행 상황판 ------------------
    elif st.session_state['page'] == 'vip_dashboard':
        st.subheader("📊 진행 상황판")
        
        raw_data = get_cached_board_data()
        
        if len(raw_data) > 1:
            df = pd.DataFrame(raw_data[1:])
            df.columns = [str(i) for i in range(len(df.columns))]
            df['sheet_row_idx'] = df.index + 2  
            
            col_f1, col_f2 = st.columns([2.5, 1])
            with col_f1:
                search_query = st.text_input("🔍 품명, 부서, 일련번호 검색", "", key="search_vip_dash")
            with col_f2:
                st.write("") 
                st.write("")
                show_completed = st.checkbox("✅ 완료 포함", value=False, key="check_vip_dash")
                
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

            st.caption("※ 표에서 확인하고자 하는 항목을 선택하세요.")
            
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
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("상태확인", use_container_width=True, type="primary"):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    
                    row_data = raw_data[sheet_row_idx - 1]
                    dialog_status_check(row_data, sheet_row_idx)

        with c2:
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

    # ------------------ VIP 전용 : 완료 확인 ------------------
    elif st.session_state['page'] == 'vip_completed':
        st.subheader("✅ 완료 확인")
        
        raw_completed = get_cached_completed_data()
        
        if len(raw_completed) > 1:
            df = pd.DataFrame(raw_completed[1:])
            df.columns = [str(i) for i in range(len(df.columns))]
            df['sheet_row_idx'] = df.index + 2
            
            display_df = pd.DataFrame()
            display_df["공장"] = df['1'] if '1' in df.columns else ""
            display_df["부서"] = df['2'] if '2' in df.columns else ""
            display_df["품명"] = df['3'] if '3' in df.columns else ""
            display_df["입고일자"] = df['7'] if '7' in df.columns else ""
            display_df["시작지연"] = df['15'] if '15' in df.columns else ""
            display_df["수령지연"] = df['16'] if '16' in df.columns else ""
            display_df["낭비시간"] = df['17'] if '17' in df.columns else ""
            
            event = st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                selection_mode="single-row",
                on_select="rerun"
            )
            selected_indices = event.selection.rows
        else:
            st.info("현재 기록된 완료 데이터가 없습니다.")
            selected_indices = []
            df = pd.DataFrame()
            
        st.write("---")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("상세확인", use_container_width=True, type="primary"):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    row_data = raw_completed[sheet_row_idx - 1]
                    dialog_completed_detail(row_data)
        with c2:
            pass # 여백
            
        st.write("")
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("🔄 새로고침", use_container_width=True):
                get_cached_completed_data.clear()
                st.rerun()
        with col_btn2:
            if st.button("⬅️ 메인으로 돌아가기", use_container_width=True):
                st.session_state['page'] = 'main'
                st.rerun()

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
        
        c1, c2, c3, c4, c5 = st.columns(5)
        
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

        with c5:
            if st.button("입고/수령 취소", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    
                    row_data = raw_data[sheet_row_idx - 1]
                    dialog_cancel_inbound_receipt(row_data, sheet_row_idx)

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
            if st.button("시작/종료 취소", use_container_width=True):
                if len(selected_indices) == 0:
                    st.warning("표에서 항목을 먼저 선택하세요.")
                else:
                    actual_row = df.iloc[selected_indices[0]]
                    sheet_row_idx = int(actual_row['sheet_row_idx'])
                    row_data = raw_data[sheet_row_idx - 1]
                    dialog_cancel_start_end(row_data, sheet_row_idx)

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

                            # 5열(의뢰자)과 8열(입고일자) 데이터는 빈 문자열로 삽입합니다.
                            new_row = [
                                next_seq, selected_factory, selected_dept, item_name.strip(),
                                "", serial_num.strip(), 1,
                                "", req_datetime_str, "", "", "", "", "", "",
                                str(uuid.uuid4())
                            ]
                            board_sheet.append_row(new_row)
                            
                            get_cached_board_data.clear() 
                            st.success("입고 생성 완료!")
                            time.sleep(1)
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
                
    # 관리자(권한 레벨 3)일 경우 화면 최하단에 유지보수 담당자 정보 표시
    if st.session_state.get('user_level') == "3":
        st.markdown("<br><br><br><div style='text-align: center; color: #C0C0C0; font-size: 13px;'>유지보수 담당자 : 김세훈</div>", unsafe_allow_html=True)
