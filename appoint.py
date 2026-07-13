
import base64
from io import StringIO

import streamlit as st

st.set_page_config(page_title="Pain Consult Diagnostic", page_icon="🩺")
st.title("Pain Consult Diagnostic")

st.success("Step 1: Streamlit ทำงานปกติ")
st.write("Streamlit version:", st.__version__)

try:
    import pandas as pd
    st.success(f"Step 2: pandas import สำเร็จ — version {pd.__version__}")
except Exception as exc:
    st.error(f"Step 2 failed: {type(exc).__name__}: {exc}")
    st.stop()

try:
    import requests
    st.success(f"Step 3: requests import สำเร็จ — version {requests.__version__}")
except Exception as exc:
    st.error(f"Step 3 failed: {type(exc).__name__}: {exc}")
    st.stop()

required = ["GITHUB_TOKEN", "GITHUB_REPO"]
missing = [key for key in required if key not in st.secrets]

if missing:
    st.error("Step 4 failed: ขาด Secrets: " + ", ".join(missing))
    st.stop()

st.success("Step 4: พบ GitHub Secrets ที่จำเป็น")
repo = st.secrets["GITHUB_REPO"]
branch = st.secrets.get("GITHUB_BRANCH", "main")
csv_path = st.secrets.get("CSV_PATH", "pain_consult_appointments.csv")
token = st.secrets["GITHUB_TOKEN"]

st.write("Repository:", repo)
st.write("Branch:", branch)
st.write("CSV path:", csv_path)

api_url = f"https://api.github.com/repos/{repo}/contents/{csv_path}"
headers = {
    "Authorization": f"Bearer {token}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

st.info("ยังไม่มีการเชื่อม GitHub จนกว่าจะกดปุ่มด้านล่าง")

if st.button("ทดสอบเชื่อมต่อ GitHub"):
    try:
        with st.spinner("กำลังเชื่อมต่อ GitHub..."):
            response = requests.get(
                api_url,
                headers=headers,
                params={"ref": branch},
                timeout=(3, 8),
            )

        st.write("HTTP status:", response.status_code)

        if response.status_code == 404:
            st.warning("Step 5: ไม่พบไฟล์ CSV แต่ GitHub API ตอบสนองปกติ")
        elif response.status_code != 200:
            st.error(f"Step 5 failed: GitHub HTTP {response.status_code}")
            st.code(response.text[:1000] or "No response body")
        else:
            st.success("Step 5: GitHub API เชื่อมต่อสำเร็จ")
            data = response.json()

            encoded = data.get("content", "")
            sha = data.get("sha", "")

            st.write("SHA available:", bool(sha))
            st.write("Encoded content available:", bool(encoded))

            if encoded:
                decoded = base64.b64decode(encoded).decode("utf-8-sig")
                st.write("CSV text length:", len(decoded))

                try:
                    df = pd.read_csv(StringIO(decoded), dtype=str).fillna("")
                    st.success(
                        f"Step 6: อ่าน CSV สำเร็จ — {len(df)} rows, "
                        f"{len(df.columns)} columns"
                    )
                    st.dataframe(df.head(5), use_container_width=True)
                except Exception as exc:
                    st.error(
                        f"Step 6 failed: {type(exc).__name__}: {exc}"
                    )
            else:
                st.warning("Step 6: ไฟล์ไม่มี content")
    except requests.Timeout:
        st.error("Step 5 failed: GitHub request timeout")
    except requests.RequestException as exc:
        st.error(f"Step 5 failed: {type(exc).__name__}: {exc}")
    except Exception as exc:
        st.error(f"Unexpected error: {type(exc).__name__}: {exc}")



