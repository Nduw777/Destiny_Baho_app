import streamlit as st
import pandas as pd
from datetime import datetime, date
import os, time

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

# ------------------------
# PAGE CONFIG
# ------------------------
st.set_page_config(
    page_title="Product Recorder",
    page_icon="📦",
    layout="centered"
)

# ------------------------
# SESSION STATE
# ------------------------
for k in ["authorized", "sheet_id"]:
    if k not in st.session_state:
        st.session_state[k] = False if k == "authorized" else None

# ------------------------
# CONFIG
# ------------------------
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets"
]

LICENSE_SHEET_ID = "11Mnt5aQrYZBEEqtKfpaxJxgh0E4VlrBUQgzJeeEzDuQ"
APP_SHEET_NAME = "Product Records"

# ------------------------
# SERVICE ACCOUNT AUTH
# ------------------------
creds = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],  # make sure secrets.toml has your service account JSON
    scopes=SCOPES
)
sheets = build("sheets", "v4", credentials=creds)
drive = build("drive", "v3", credentials=creds)

# ------------------------
# LICENSE CHECK FUNCTION
# ------------------------
def check_license(key):
    try:
        rows = sheets.spreadsheets().values().get(
            spreadsheetId=LICENSE_SHEET_ID,
            range="A2:D"
        ).execute().get("values", [])
    except HttpError:
        return False, "Cannot access license sheet"

    for r in rows:
        r += [""] * (4 - len(r))
        lic, email, status, expiry = r
        if lic == key:
            if status != "ACTIVE":
                return False, "License inactive"
            # Optional: You can remove email check if service account is universal
            if date.today() > datetime.strptime(expiry, "%Y-%m-%d").date():
                return False, "License expired"
            return True, "OK"

    return False, "License not found"

# ------------------------
# LICENSE PAGE
# ------------------------
if not st.session_state.authorized:
    st.title("🔑 License")
    lic = st.text_input("Enter License Key")
    if st.button("Enter App"):
        ok, msg = check_license(lic)
        if ok:
            st.session_state.authorized = True
            st.success("Access granted 🎉")
            st.experimental_rerun()
        else:
            st.error(msg)
    st.stop()

# ------------------------
# CREATE OR GET PRODUCT SHEET
# ------------------------
def get_or_create_sheet():
    query = f"name='{APP_SHEET_NAME}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    res = drive.files().list(q=query, fields="files(id)").execute()
    files = res.get("files", [])

    if files:
        return files[0]["id"]

    file = drive.files().create(
        body={"name": APP_SHEET_NAME, "mimeType": "application/vnd.google-apps.spreadsheet"},
        fields="id"
    ).execute()

    sheet_id = file["id"]
    headers = [[
        "Date", "Product", "Selling price", "Cost price",
        "Quantity", "Revenue", "Profit",
        "Image Preview", "Image Link"
    ]]
    sheets.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A1",
        valueInputOption="RAW",
        body={"values": headers}
    ).execute()

    return sheet_id

if not st.session_state.sheet_id:
    st.session_state.sheet_id = get_or_create_sheet()
SHEET_ID = st.session_state.sheet_id

# ------------------------
# IMAGE UPLOAD
# ------------------------
def upload_image(path):
    file = drive.files().create(
        body={"name": os.path.basename(path)},
        media_body=MediaFileUpload(path),
        fields="id"
    ).execute()
    file_id = file["id"]
    drive.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"}
    ).execute()
    return f"https://drive.google.com/uc?id={file_id}"

# ------------------------
# RESIZE ROW FOR IMAGE
# ------------------------
def resize_last_row(sheet_id, row_index):
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{
            "updateDimensionProperties": {
                "range": {"sheetId": 0, "dimension": "ROWS", "startIndex": row_index - 1, "endIndex": row_index},
                "properties": {"pixelSize": 45},
                "fields": "pixelSize"
            }
        }]}
    ).execute()

# ------------------------
# SHEET FORMATTER
# ------------------------
def format_sheet(sheet_id):
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [

            # HEADER STYLE
            {"repeatCell": {
                "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {"userEnteredFormat": {"backgroundColor":{"red":0.85,"green":0.92,"blue":1},"textFormat":{"bold":True}}},
                "fields": "userEnteredFormat(backgroundColor,textFormat)"
            }},

            # COLUMN WIDTHS
            {"updateDimensionProperties": {
                "range": {"sheetId":0,"dimension":"COLUMNS","startIndex":0,"endIndex":9},
                "properties":{"pixelSize":95},
                "fields":"pixelSize"
            }},

            # IMAGE COLUMN WIDER
            {"updateDimensionProperties": {
                "range":{"sheetId":0,"dimension":"COLUMNS","startIndex":7,"endIndex":8},
                "properties":{"pixelSize":140},
                "fields":"pixelSize"
            }}
        ]}
    ).execute()

# ------------------------
# DASHBOARD
# ------------------------
st.title("📦 Product Recorder")
st.caption("Mobile friendly mode enabled 📱")
tab1, tab2 = st.tabs(["✍️📖 Add Product/IGICURUZWA", "📊 Records/UBUBIKO"])

# ---------- ADD PRODUCT ----------
with tab1:
    if "reset_form" not in st.session_state:
        st.session_state.reset_form = False
    if st.session_state.reset_form:
        st.session_state.product_name = ""
        st.session_state.selling_price = 0.0
        st.session_state.cost_price = 0.0
        st.session_state.quantity = 1
        st.session_state.reset_form = False

    img = st.camera_input("Take product photo/ISHUSHO")
    name = st.text_input("Product name/IZINA RYI IGICURUZWA", key="product_name")
    price = st.number_input("Selling price/IKIGUZI", 0.0, key="selling_price")
    cost = st.number_input("Cost price/IKIRANGUZO", 0.0, key="cost_price")
    qty = st.number_input("Quantity/INGANO", 1, key="quantity")

    revenue = price * qty
    profit = (price - cost) * qty

    st.info(f"Revenue/AYINJIYE: {revenue}")
    st.info(f"Profit/INYUNGU: {profit}")

    if st.button("Save/BIKA", use_container_width=True):
        if img and name:
            path = f"{name}_{int(time.time())}.png"
            with open(path, "wb") as f:
                f.write(img.getbuffer())
            img_link = upload_image(path)

            data = sheets.spreadsheets().values().get(
                spreadsheetId=SHEET_ID, range="A:I"
            ).execute().get("values", [])

            if data and data[-1][0] == "TOTAL":
                sheets.spreadsheets().values().clear(
                    spreadsheetId=SHEET_ID, range=f"A{len(data)}:I{len(data)}"
                ).execute()
                data.pop()

            row = [[
                datetime.now().strftime("%Y-%m-%d %H:%M"),
                name, price, cost, qty,
                revenue, profit,
                f'=IMAGE("{img_link}")',
                f'=HYPERLINK("{img_link}","View Image")'
            ]]
            sheets.spreadsheets().values().append(
                spreadsheetId=SHEET_ID,
                range="A:I",
                valueInputOption="USER_ENTERED",
                body={"values": row}
            ).execute()

            last_row = len(data) + 1
            totals = [[
                "TOTAL","","","",
                f"=SUM(E2:E{last_row})",
                f"=SUM(F2:F{last_row})",
                f"=SUM(G2:G{last_row})",
                "", ""
            ]]
            sheets.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=f"A{last_row+1}:I{last_row+1}",
                valueInputOption="USER_ENTERED",
                body={"values": totals}
            ).execute()

            resize_last_row(SHEET_ID, last_row)
            format_sheet(SHEET_ID)

            st.success("Saved Successfully ✅")
            st.session_state.reset_form = True
            st.experimental_rerun()

# ---------- VIEW ----------
with tab2:
    data = sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID, range="A:I"
    ).execute().get("values", [])

    if len(data) > 1:
        headers = ["Date","Product","Selling price","Cost price","Quantity","Revenue","Profit","Image Preview","Image Link"]
        rows = data[1:]
        fixed_rows = [r[:9] + [""]*(9-len(r)) for r in rows]
        df = pd.DataFrame(fixed_rows, columns=headers)
        for c in ["Selling price","Cost price","Quantity","Revenue","Profit"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        st.dataframe(df, use_container_width=True)
        st.success(f"Total Revenue: {df['Revenue'].sum()}")
        st.success(f"Total Profit: {df['Profit'].sum()}")
    else:
        st.info("No records yet")
