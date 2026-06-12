# app.py
import streamlit as st
import pandas as pd
import requests, base64
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

BKK = ZoneInfo("Asia/Bangkok")

GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
REPO = st.secrets["GITHUB_REPO"]          # เช่น "username/repo"
BRANCH = st.secrets.get("GITHUB_BRANCH", "main")
CSV_PATH = st.secrets.get("CSV_PATH", "pain_consult_appointments.csv")

API_URL = f"https://api.github.com/repos/{REPO}/contents/{CSV_PATH}"

HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

COLUMNS = [
    "created_at_bkk", "updated_at_bkk",
    "first_name", "last_name", "email",
    "appointment_date", "appointment_time",
    "status", "action_count"
]

CONTACT_MSG = "โปรดติดต่อสถานพยาบาล ในเวลาทำการ ที่หมายเลข 034351611"


def now_bkk():
    return datetime.now(BKK).strftime("%Y-%m-%d %H:%M:%S")


def load_csv():
    r = requests.get(API_URL, headers=HEADERS, params={"ref": BRANCH})
    if r.status_code == 404:
        return pd.DataFrame(columns=COLUMNS), None

    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    from io import StringIO
    df = pd.read_csv(StringIO(content), dtype=str).fillna("")
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNS], data["sha"]


def save_csv(df, sha=None):
    csv_text = df.to_csv(index=False)
    encoded = base64.b64encode(csv_text.encode("utf-8")).decode("utf-8")

    payload = {
        "message": f"update pain consult appointments {now_bkk()}",
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(API_URL, headers=HEADERS, json=payload)
    r.raise_for_status()


def working_days_next_month():
    today = datetime.now(BKK).date()
    days = []
    for i in range(1, 32):
        d = today + timedelta(days=i)
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
    return days


def is_slot_taken(df, appt_date, exclude_email=None):
    active = df[df["status"].isin(["booked", "rescheduled"])]
    active = active[active["appointment_date"] == appt_date.isoformat()]
    if exclude_email:
        active = active[active["email"].str.lower() != exclude_email.lower()]
    return len(active) > 0


def email_action_count(df, email):
    rows = df[df["email"].str.lower() == email.lower()]
    if rows.empty:
        return 0
    return pd.to_numeric(rows["action_count"], errors="coerce").fillna(0).max().astype(int)


def get_active_booking(df, email):
    rows = df[
        (df["email"].str.lower() == email.lower()) &
        (df["status"].isin(["booked", "rescheduled"]))
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

df, sha = load_csv()

tab1, tab2 = st.tabs(["นัดหมายใหม่", "แก้ไข / ยกเลิกนัดหมาย"])

with tab1:
    st.write("### กรอกข้อมูลเพื่อนัดหมาย")

    first = st.text_input("ชื่อ")
    last = st.text_input("นามสกุล")
    email = st.text_input("อีเมล์").strip().lower()

    available_days = [
        d for d in working_days_next_month()
        if not is_slot_taken(df, d)
    ]

    if not available_days:
        st.warning("ขณะนี้ไม่มีวันว่างใน 1 เดือนข้างหน้า")
    else:
        chosen_date = st.selectbox(
            "เลือกวันนัดหมาย",
            available_days,
            format_func=lambda d: d.strftime("%d/%m/%Y")
        )

        st.write("เวลา: **07.00-08.30 น.**")

        if st.button("ยืนยันนัดหมาย"):
            if not first or not last or not email:
                st.error("กรุณากรอกชื่อ นามสกุล และอีเมล์ให้ครบ")
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
                    "first_name": first,
                    "last_name": last,
                    "email": email,
                    "appointment_date": chosen_date.isoformat(),
                    "appointment_time": "07:00-08:30",
                    "status": "booked",
                    "action_count": str(count),
                }
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_csv(df, sha)
                st.success(f"นัดหมายสำเร็จ วันที่ {chosen_date.strftime('%d/%m/%Y')} เวลา 07.00-08.30 น.")

with tab2:
    st.write("### แก้ไขหรือยกเลิกนัดหมาย")
    edit_email = st.text_input("ใส่อีเมล์ที่ใช้จอง", key="edit_email_input").strip().lower()

    if st.button("ค้นหานัดหมาย"):
        if not edit_email:
            st.error("กรุณาใส่อีเมล์")
        else:
            idx = get_active_booking(df, edit_email)
            if idx is None:
                st.warning("ไม่พบนัดหมายที่ยังใช้งานอยู่")
                if "edit_idx" in st.session_state:
                    del st.session_state["edit_idx"]
            else:
                st.session_state["edit_idx"] = int(idx)

    if "edit_idx" in st.session_state:
        idx = st.session_state["edit_idx"]
        row = df.loc[idx]

        appt_date = datetime.strptime(row["appointment_date"], "%Y-%m-%d").date()
        today = datetime.now(BKK).date()

        st.write(f"นัดหมายปัจจุบัน: **{appt_date.strftime('%d/%m/%Y')} เวลา 07.00-08.30 น.**")

        if appt_date <= today:
            st.error("ไม่สามารถแก้ไขหรือยกเลิกได้ในวันนัดหมายหรือหลังวันนัดหมายแล้ว")
        elif int(row["action_count"]) >= 2:
            st.error(CONTACT_MSG)
        else:
            choice = st.radio("เลือกการดำเนินการ", ["เปลี่ยนวันนัด", "ยกเลิกนัด"])

            if choice == "เปลี่ยนวันนัด":
                new_days = [
                    d for d in working_days_next_month()
                    if not is_slot_taken(df, d, exclude_email=row["email"])
                ]

                new_date = st.selectbox(
                    "เลือกวันนัดใหม่",
                    new_days,
                    format_func=lambda d: d.strftime("%d/%m/%Y")
                )

                if st.button("ยืนยันเปลี่ยนวันนัด"):
                    df.at[idx, "appointment_date"] = new_date.isoformat()
                    df.at[idx, "status"] = "rescheduled"
                    df.at[idx, "updated_at_bkk"] = now_bkk()
                    df.at[idx, "action_count"] = str(int(row["action_count"]) + 1)
                    save_csv(df, sha)
                    st.success(f"เปลี่ยนนัดสำเร็จ เป็นวันที่ {new_date.strftime('%d/%m/%Y')} เวลา 07.00-08.30 น.")

            if choice == "ยกเลิกนัด":
                if st.button("ยืนยันยกเลิกนัดหมาย"):
                    df.at[idx, "status"] = "cancelled"
                    df.at[idx, "updated_at_bkk"] = now_bkk()
                    df.at[idx, "action_count"] = str(int(row["action_count"]) + 1)
                    save_csv(df, sha)
                    st.success("ยกเลิกนัดหมายสำเร็จ")
