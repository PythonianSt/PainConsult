import base64
from datetime import datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BKK = ZoneInfo("Asia/Bangkok")

GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
REPO = st.secrets["GITHUB_REPO"]
BRANCH = st.secrets.get("GITHUB_BRANCH", "main")
CSV_PATH = st.secrets.get("CSV_PATH", "pain_consult_appointments.csv")

API_URL = f"https://api.github.com/repos/{REPO}/contents/{CSV_PATH}"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

COLUMNS = [
    "created_at_bkk", "updated_at_bkk",
    "first_name", "last_name", "email",
    "appointment_date", "appointment_time",
    "status", "action_count",
]

CONTACT_MSG = "โปรดติดต่อสถานพยาบาล ในเวลาทำการ ที่หมายเลข 034351611"
GITHUB_ERROR_MSG = (
    "ระบบเชื่อมต่อฐานข้อมูล GitHub ไม่สำเร็จชั่วคราว "
    "กรุณาลองใหม่อีกครั้งภายหลัง หรือโทรติดต่อสถานพยาบาลที่ 034351611"
)


def now_bkk():
    return datetime.now(BKK).strftime("%Y-%m-%d %H:%M:%S")


def empty_df():
    return pd.DataFrame(columns=COLUMNS)


def github_session():
    session = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "PUT"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


SESSION = github_session()


def load_csv():
    """Return (dataframe, sha, error_message). Never crashes the whole app."""
    try:
        r = SESSION.get(
            API_URL,
            headers=HEADERS,
            params={"ref": BRANCH},
            timeout=(10, 30),
        )

        if r.status_code == 404:
            return empty_df(), None, None

        if r.status_code != 200:
            detail = r.text[:300] if r.text else "No response body"
            return empty_df(), None, f"GitHub HTTP {r.status_code}: {detail}"

        data = r.json()
        raw_content = data.get("content", "")
        if not raw_content:
            return empty_df(), data.get("sha"), None

        content = base64.b64decode(raw_content).decode("utf-8-sig")
        if not content.strip():
            return empty_df(), data.get("sha"), None

        df = pd.read_csv(StringIO(content), dtype=str).fillna("")
        for c in COLUMNS:
            if c not in df.columns:
                df[c] = ""

        return df[COLUMNS], data.get("sha"), None

    except (requests.RequestException, ValueError, KeyError, UnicodeDecodeError) as exc:
        return empty_df(), None, f"{type(exc).__name__}: {exc}"


def get_current_sha():
    try:
        r = SESSION.get(
            API_URL,
            headers=HEADERS,
            params={"ref": BRANCH},
            timeout=(10, 30),
        )
        if r.status_code == 404:
            return None
        if r.status_code != 200:
            return None
        return r.json().get("sha")
    except (requests.RequestException, ValueError):
        return None


def save_csv(df, sha=None):
    """Save CSV and return (success, error_message)."""
    csv_text = df.to_csv(index=False)
    encoded = base64.b64encode(csv_text.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"update pain consult appointments {now_bkk()}",
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    try:
        r = SESSION.put(
            API_URL,
            headers=HEADERS,
            json=payload,
            timeout=(10, 30),
        )

        # Another user may have updated the CSV after this page loaded.
        if r.status_code in (409, 422):
            latest_sha = get_current_sha()
            if latest_sha:
                payload["sha"] = latest_sha
                r = SESSION.put(
                    API_URL,
                    headers=HEADERS,
                    json=payload,
                    timeout=(10, 30),
                )

        if r.status_code not in (200, 201):
            detail = r.text[:300] if r.text else "No response body"
            return False, f"GitHub HTTP {r.status_code}: {detail}"

        return True, None

    except requests.RequestException as exc:
        return False, f"{type(exc).__name__}: {exc}"


def working_days_next_month():
    today = datetime.now(BKK).date()
    return [
        today + timedelta(days=i)
        for i in range(1, 32)
        if (today + timedelta(days=i)).weekday() < 5
    ]


def is_slot_taken(df, appt_date, exclude_email=None):
    active = df[df["status"].isin(["booked", "rescheduled"])]
    active = active[active["appointment_date"] == appt_date.isoformat()]
    if exclude_email:
        active = active[active["email"].str.lower() != exclude_email.lower()]
    return not active.empty


def email_action_count(df, email):
    rows = df[df["email"].str.lower() == email.lower()]
    if rows.empty:
        return 0
    values = pd.to_numeric(rows["action_count"], errors="coerce").fillna(0)
    return int(values.max())


def get_active_booking(df, email):
    rows = df[
        (df["email"].str.lower() == email.lower())
        & (df["status"].isin(["booked", "rescheduled"]))
    ]
    if rows.empty:
        return None
    return rows.tail(1).index[0]


st.set_page_config(page_title="Pain Consult Appointment", page_icon="🩺")

st.title("🩺 นัดหมาย Pain Consult KU KPS Infirmary")
st.subheader("สถานพยาบาล มหาวิทยาลัยเกษตรศาสตร์ วิทยาเขตกำแพงแสน")

st.info(
    """
**วัตถุประสงค์ของ Pain Consult**  
ดูแลบำบัดความปวดจากการเล่นกีฬา ปวดศีรษะ ปวดประจำเดือน และปวดเรื้อรัง  
ในช่วงเวลาก่อนเริ่มเรียน/งาน เวลา **07.00-08.30 น.**
"""
)

df, sha, load_error = load_csv()
database_ready = load_error is None

if not database_ready:
    st.error(GITHUB_ERROR_MSG)
    with st.expander("รายละเอียดสำหรับผู้ดูแลระบบ"):
        st.code(load_error)
    if st.button("ลองเชื่อมต่อใหม่"):
        st.rerun()

# Keep the page visible, but prohibit booking against an unknown/empty dataset.
tab1, tab2 = st.tabs(["นัดหมายใหม่", "แก้ไข / ยกเลิกนัดหมาย"])

with tab1:
    st.write("### กรอกข้อมูลเพื่อนัดหมาย")

    first = st.text_input("ชื่อ", disabled=not database_ready)
    last = st.text_input("นามสกุล", disabled=not database_ready)
    email = st.text_input("อีเมล์", disabled=not database_ready).strip().lower()

    available_days = []
    if database_ready:
        available_days = [
            d for d in working_days_next_month()
            if not is_slot_taken(df, d)
        ]

    if not database_ready:
        st.warning("ปิดการนัดหมายชั่วคราว เพื่อป้องกันการจองซ้ำขณะอ่านฐานข้อมูลไม่ได้")
    elif not available_days:
        st.warning("ขณะนี้ไม่มีวันว่างใน 1 เดือนข้างหน้า")
    else:
        chosen_date = st.selectbox(
            "เลือกวันนัดหมาย",
            available_days,
            format_func=lambda d: d.strftime("%d/%m/%Y"),
        )

        st.write("เวลา: **07.00-08.30 น.**")

        if st.button("ยืนยันนัดหมาย", disabled=not database_ready):
            if not first or not last or not email:
                st.error("กรุณากรอกชื่อ นามสกุล และอีเมล์ให้ครบ")
            elif "@" not in email or "." not in email.split("@")[-1]:
                st.error("กรุณาตรวจสอบรูปแบบอีเมล์")
            elif email_action_count(df, email) >= 2:
                st.error(CONTACT_MSG)
            elif get_active_booking(df, email) is not None:
                st.error("อีเมล์นี้มีนัดหมายอยู่แล้ว กรุณาไปที่เมนูแก้ไข / ยกเลิกนัดหมาย")
            elif is_slot_taken(df, chosen_date):
                st.error("วันดังกล่าวมีผู้จองแล้ว กรุณาเลือกวันอื่น")
            else:
                count = email_action_count(df, email) + 1
                new_row = {
                    "created_at_bkk": now_bkk(),
                    "updated_at_bkk": now_bkk(),
                    "first_name": first.strip(),
                    "last_name": last.strip(),
                    "email": email,
                    "appointment_date": chosen_date.isoformat(),
                    "appointment_time": "07:00-08:30",
                    "status": "booked",
                    "action_count": str(count),
                }
                updated_df = pd.concat(
                    [df, pd.DataFrame([new_row])], ignore_index=True
                )
                success, save_error = save_csv(updated_df, sha)
                if success:
                    st.success(
                        f"นัดหมายสำเร็จ วันที่ {chosen_date.strftime('%d/%m/%Y')} "
                        "เวลา 07.00-08.30 น."
                    )
                    st.balloons()
                else:
                    st.error(GITHUB_ERROR_MSG)
                    with st.expander("รายละเอียดสำหรับผู้ดูแลระบบ"):
                        st.code(save_error)

with tab2:
    st.write("### แก้ไขหรือยกเลิกนัดหมาย")
    edit_email = st.text_input(
        "ใส่อีเมล์ที่ใช้จอง",
        key="edit_email_input",
        disabled=not database_ready,
    ).strip().lower()

    if st.button("ค้นหานัดหมาย", disabled=not database_ready):
        if not edit_email:
            st.error("กรุณาใส่อีเมล์")
        else:
            idx = get_active_booking(df, edit_email)
            if idx is None:
                st.warning("ไม่พบนัดหมายที่ยังใช้งานอยู่")
                st.session_state.pop("edit_idx", None)
            else:
                st.session_state["edit_idx"] = int(idx)

    if database_ready and "edit_idx" in st.session_state:
        idx = st.session_state["edit_idx"]

        if idx not in df.index:
            st.session_state.pop("edit_idx", None)
            st.warning("ข้อมูลนัดหมายมีการเปลี่ยนแปลง กรุณาค้นหาใหม่")
        else:
            row = df.loc[idx]
            try:
                appt_date = datetime.strptime(
                    row["appointment_date"], "%Y-%m-%d"
                ).date()
                action_count = int(float(row.get("action_count", 0) or 0))
            except (TypeError, ValueError):
                st.error("ข้อมูลนัดหมายรายการนี้ไม่สมบูรณ์ กรุณาติดต่อสถานพยาบาล")
                st.stop()

            today = datetime.now(BKK).date()
            st.write(
                f"นัดหมายปัจจุบัน: **{appt_date.strftime('%d/%m/%Y')} "
                "เวลา 07.00-08.30 น.**"
            )

            if appt_date <= today:
                st.error("ไม่สามารถแก้ไขหรือยกเลิกได้ในวันนัดหมายหรือหลังวันนัดหมายแล้ว")
            elif action_count >= 2:
                st.error(CONTACT_MSG)
            else:
                choice = st.radio(
                    "เลือกการดำเนินการ", ["เปลี่ยนวันนัด", "ยกเลิกนัด"]
                )

                if choice == "เปลี่ยนวันนัด":
                    new_days = [
                        d for d in working_days_next_month()
                        if not is_slot_taken(df, d, exclude_email=row["email"])
                    ]

                    if not new_days:
                        st.warning("ขณะนี้ไม่มีวันอื่นว่างใน 1 เดือนข้างหน้า")
                    else:
                        new_date = st.selectbox(
                            "เลือกวันนัดใหม่",
                            new_days,
                            format_func=lambda d: d.strftime("%d/%m/%Y"),
                        )

                        if st.button("ยืนยันเปลี่ยนวันนัด"):
                            updated_df = df.copy()
                            updated_df.at[idx, "appointment_date"] = new_date.isoformat()
                            updated_df.at[idx, "status"] = "rescheduled"
                            updated_df.at[idx, "updated_at_bkk"] = now_bkk()
                            updated_df.at[idx, "action_count"] = str(action_count + 1)
                            success, save_error = save_csv(updated_df, sha)
                            if success:
                                st.success(
                                    f"เปลี่ยนนัดสำเร็จ เป็นวันที่ "
                                    f"{new_date.strftime('%d/%m/%Y')} เวลา 07.00-08.30 น."
                                )
                                st.session_state.pop("edit_idx", None)
                            else:
                                st.error(GITHUB_ERROR_MSG)
                                with st.expander("รายละเอียดสำหรับผู้ดูแลระบบ"):
                                    st.code(save_error)

                elif choice == "ยกเลิกนัด":
                    if st.button("ยืนยันยกเลิกนัดหมาย"):
                        updated_df = df.copy()
                        updated_df.at[idx, "status"] = "cancelled"
                        updated_df.at[idx, "updated_at_bkk"] = now_bkk()
                        updated_df.at[idx, "action_count"] = str(action_count + 1)
                        success, save_error = save_csv(updated_df, sha)
                        if success:
                            st.success("ยกเลิกนัดหมายสำเร็จ")
                            st.session_state.pop("edit_idx", None)
                        else:
                            st.error(GITHUB_ERROR_MSG)
                            with st.expander("รายละเอียดสำหรับผู้ดูแลระบบ"):
                                st.code(save_error)

