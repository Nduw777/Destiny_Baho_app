import streamlit as st
import pandas as pd
from datetime import datetime, date
import os, time
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
import pickle

# ------------------------
# PAGE CONFIG
# ------------------------
st.set_page_config(
    page_title="Product Recorder",
    page_icon="📦",
    layout="centered"
)
# ------------------------
# HIDE STREAMLIT BRANDING
# ------------------------
hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {visibility: hidden;}
    [data-testid="stDecoration"] {visibility: hidden;}
    .stActionButton {visibility: hidden;}
    </style>
    """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ------------------------
# SESSION STATE
# ------------------------
for k in ["authorized", "user_email", "sheet_id", "credentials"]:
    if k not in st.session_state:
        st.session_state[k] = None if k != "authorized" else False

# ------------------------
# CONFIG
# ------------------------
scopes = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets"
]

LICENSE_SHEET_ID = "1JRbHa4STLSwOhkePqcSerpnuEvxUqMTePFY_SCSrngg"
APP_SHEET_NAME = "Product Records"
PARENT_FOLDER_NAME = "Product Recorder User Sheets"

# ------------------------
# OAUTH LOGIN
# ------------------------
if not st.session_state.credentials:
    st.title("🔑 Google Login Required")

    # Properly format the client config for Flow
    client_config = {
        "web": {
            "client_id": st.secrets["oauth_credentials"]["client_id"],
            "project_id": st.secrets["oauth_credentials"]["project_id"],
            "auth_uri": st.secrets["oauth_credentials"]["auth_uri"],
            "token_uri": st.secrets["oauth_credentials"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["oauth_credentials"]["auth_provider_x509_cert_url"],
            "client_secret": st.secrets["oauth_credentials"]["client_secret"],
            "redirect_uris": st.secrets["oauth_credentials"]["redirect_uris"]
        }
    }

    if "code" not in st.query_params:
        flow = Flow.from_client_config(
            client_config,
            scopes=scopes,
            redirect_uri=st.secrets["oauth_credentials"]["redirect_uris"][0]
        )
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        st.markdown(f"[Click here to login with Google]({auth_url})")
        st.stop()
    else:
        code = st.query_params["code"]
        flow = Flow.from_client_config(
            client_config,
            scopes=scopes,
            redirect_uri=st.secrets["oauth_credentials"]["redirect_uris"][0]
        )
        flow.fetch_token(code=code)
        st.session_state.credentials = flow.credentials
        st.rerun()

creds = st.session_state.credentials
sheets = build("sheets", "v4", credentials=creds)
drive = build("drive", "v3", credentials=creds)

# ------------------------
# GET USER EMAIL
# ------------------------
if not st.session_state.user_email:
    about = drive.about().get(fields="user").execute()
    st.session_state.user_email = about["user"]["emailAddress"]

# ------------------------
# LICENSE CHECK
# ------------------------
def check_license(key):
    try:
        rows = sheets.spreadsheets().values().get(
            spreadsheetId=LICENSE_SHEET_ID,
            range="A2:D"
        ).execute().get("values", [])
    except HttpError:
        return False, "No permission to read license sheet"

    for r in rows:
        r += [""] * (4 - len(r))
        lic, email, status, expiry = r
        if lic == key:
            if status != "ACTIVE":
                return False, "License inactive"
            if email != st.session_state.user_email:
                return False, "Email not allowed"
            if date.today() > datetime.strptime(expiry, "%Y-%m-%d").date():
                return False, "License expired"
            return True, "OK"
    return False, "License not found"

# ------------------------
# LICENSE PAGE
# ------------------------
if not st.session_state.authorized:
    st.title("🔑 License")
    st.write(f"Signed in as **{st.session_state.user_email}**")
    lic = st.text_input("Enter License Key")
    if st.button("Enter App"):
        ok, msg = check_license(lic)
        if ok:
            st.session_state.authorized = True
            st.success("Access granted 🎉")
            st.rerun()
        else:
            st.error(msg)
    st.stop()

# ------------------------
# CREATE OR GET SHEET (user personal folder)
# ------------------------
def get_or_create_folder(name):
    results = drive.files().list(
        q=f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)"
    ).execute()
    files = results.get("files", [])
    if files:
        return files[0]["id"]
    file = drive.files().create(
        body={"name": name, "mimeType": "application/vnd.google-apps.folder"},
        fields="id"
    ).execute()
    return file["id"]

USER_FOLDER_ID = get_or_create_folder(PARENT_FOLDER_NAME)

def get_or_create_sheet():
    query = f"'{USER_FOLDER_ID}' in parents and name='{APP_SHEET_NAME}' and trashed=false"
    res = drive.files().list(q=query, fields="files(id)").execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]

    file = drive.files().create(
        body={
            "name": APP_SHEET_NAME,
            "mimeType": "application/vnd.google-apps.spreadsheet",
            "parents": [USER_FOLDER_ID]
        },
        fields="id"
    ).execute()
    sheet_id = file["id"]

    headers = [[
        "Date","Customer_name","Product","Selling price","Cost price",
        "Quantity","Revenue","Profit","Image Preview","Image Link"
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
        body={"name": os.path.basename(path), "parents": [USER_FOLDER_ID]},
        media_body=MediaFileUpload(path),
        fields="id"
    ).execute()
    file_id = file["id"]
    drive.permissions().create(fileId=file_id, body={"role": "reader","type":"anyone"}).execute()
    return f"https://drive.google.com/uc?id={file_id}"

# ------------------------
# RESIZE & FORMAT SHEET
# ------------------------
def resize_last_row(sheet_id, row_index):
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"updateDimensionProperties": {"range": {"sheetId":0,"dimension":"ROWS","startIndex":row_index-1,"endIndex":row_index},"properties":{"pixelSize":45},"fields":"pixelSize"}}]}
    ).execute()

def format_sheet(sheet_id):
    sheets.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests":[
            {"repeatCell":{"range":{"sheetId":0,"startRowIndex":0,"endRowIndex":1},"cell":{"userEnteredFormat":{"backgroundColor":{"red":0.85,"green":0.92,"blue":1},"textFormat":{"bold":True}}},"fields":"userEnteredFormat(backgroundColor,textFormat)"}},
            {"updateDimensionProperties":{"range":{"sheetId":0,"dimension":"COLUMNS","startIndex":0,"endIndex":9},"properties":{"pixelSize":95},"fields":"pixelSize"}},
            {"updateDimensionProperties":{"range":{"sheetId":0,"dimension":"COLUMNS","startIndex":7,"endIndex":8},"properties":{"pixelSize":140},"fields":"pixelSize"}}
        ]}
    ).execute()

# ------------------------
# DASHBOARD
# ------------------------
st.title("📦 Product Recorder")
st.caption("Mobile friendly mode enabled 📱")
tab1, tab2 = st.tabs(["✍️📖 Add Product/IGICURUZWA", "📊 Records/UBUBIKO"])

# Add Product Tab
with tab1:
    if "reset_form" not in st.session_state:
        st.session_state.reset_form = False
    if st.session_state.reset_form:
        st.session_state.Customer_name = ""
        st.session_state.product_name = ""
        st.session_state.selling_price = 0.0
        st.session_state.cost_price = 0.0
        st.session_state.quantity = 1
        st.session_state.reset_form = False

    img = st.camera_input("Take product photo/ISHUSHO")
    name_ = st.text_input("Customer_name/IZINA RY'UMUKIRIYA", key="Customer_name")
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

            data = sheets.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="A:J").execute().get("values", [])
            if data and data[-1][0] == "TOTAL":
                sheets.spreadsheets().values().clear(spreadsheetId=SHEET_ID, range=f"A{len(data)}:I{len(data)}").execute()
                data.pop()

            row = [[datetime.now().strftime("%Y-%m-%d %H:%M"), name_,name, price, cost, qty, revenue, profit,
                    f'=IMAGE("{img_link}")', f'=HYPERLINK("{img_link}","View Image")']]
            sheets.spreadsheets().values().append(spreadsheetId=SHEET_ID, range="A:J", valueInputOption="USER_ENTERED", body={"values": row}).execute()

            last_product_row = len(data)+1
            totals = [["TOTAL","","","",f"=SUM(E2:E{last_product_row})",f"=SUM(F2:F{last_product_row})",f"=SUM(G2:G{last_product_row})","",""]]
            sheets.spreadsheets().values().update(spreadsheetId=SHEET_ID, range=f"A{last_product_row+1}:I{last_product_row+1}", valueInputOption="USER_ENTERED", body={"values": totals}).execute()

            resize_last_row(SHEET_ID, last_product_row)
            format_sheet(SHEET_ID)
            st.success("Saved Successful✅")
            st.session_state.reset_form = True
            st.rerun()
        else:
            st.error("Please capture an image and enter product name")

# View Records Tab
with tab2:
    data = sheets.spreadsheets().values().get(spreadsheetId=SHEET_ID, range="A:J").execute().get("values", [])
    if len(data) > 1:
        headers = ["Date","Customer_name","Product","Selling price","Cost price","Quantity","Revenue","Profit","Image Preview","Image Link"]
        rows = data[1:]
        fixed_rows = [r[:9]+[""]*(9-len(r)) for r in rows]
        df = pd.DataFrame(fixed_rows, columns=headers)
        for c in ["Selling price","Cost price","Quantity","Revenue","Profit"]:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
        st.dataframe(df, use_container_width=True)
        st.success(f"Total Revenue: {df['Revenue'].sum()}")
        st.success(f"Total Profit: {df['Profit'].sum()}")
    else:
        st.info("No records yet")
