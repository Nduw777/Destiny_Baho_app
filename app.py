import streamlit as st
import pandas as pd
from datetime import datetime, date
import os, time

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Product Recorder", page_icon="📦")

# ---------------- SESSION ----------------
for k in ["authorized","user_email","sheet_id"]:
    if k not in st.session_state:
        st.session_state[k] = None if k!="authorized" else False

# ---------------- CONFIG ----------------
LICENSE_SHEET_ID = "1JRbHa4STLSwOhkePqcSerpnuEvxUqMTePFY_SCSrngg"
APP_SHEET_NAME = "Product Records"
PARENT_FOLDER_ID = "1OiW-zHuVky36D62GO8ziezlRYyqoIT1R"

SCOPES=[
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]

# ---------------- AUTH ----------------
creds = service_account.Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)

sheets = build("sheets","v4",credentials=creds)
drive = build("drive","v3",credentials=creds)

# ---------------- EMAIL INPUT ----------------
if not st.session_state.user_email:
    st.session_state.user_email = st.text_input("Enter your email")
    if not st.session_state.user_email:
        st.stop()

# ---------------- LICENSE CHECK ----------------
def check_license(key):
    try:
        rows = sheets.spreadsheets().values().get(
            spreadsheetId=LICENSE_SHEET_ID,
            range="A2:D"
        ).execute().get("values",[])
    except HttpError:
        return False,"Cannot read license database"

    for r in rows:
        r += [""]*(4-len(r))
        lic,email,status,expiry = r

        if lic == key:
            if status!="ACTIVE":
                return False,"License inactive"
            if email!=st.session_state.user_email:
                return False,"Wrong email"
            if date.today() > datetime.strptime(expiry,"%Y-%m-%d").date():
                return False,"License expired"
            return True,"OK"

    return False,"License not found"

# ---------------- LICENSE PAGE ----------------
if not st.session_state.authorized:
    st.title("🔑 License")

    lic = st.text_input("Enter license key")

    if st.button("Enter"):
        ok,msg = check_license(lic)
        if ok:
            st.session_state.authorized=True
            st.success("Access granted")
            st.rerun()
        else:
            st.error(msg)

    st.stop()

# ---------------- GET OR CREATE SHEET ----------------
def get_or_create_sheet():

    try:
        query=f"'{PARENT_FOLDER_ID}' in parents and name='{APP_SHEET_NAME}' and trashed=false"
        res=drive.files().list(q=query,fields="files(id)").execute()
        files=res.get("files",[])
    except HttpError:
        st.error("Drive access failed. Check folder sharing.")
        st.stop()

    if files:
        return files[0]["id"]

    # create new sheet
    try:
        file=drive.files().create(
            body={
                "name":APP_SHEET_NAME,
                "mimeType":"application/vnd.google-apps.spreadsheet",
                "parents":[PARENT_FOLDER_ID]
            },
            fields="id"
        ).execute()

        sheet_id=file["id"]

    except HttpError as e:
        if "storageQuotaExceeded" in str(e):
            st.error("Drive storage full. Contact admin.")
            st.stop()
        else:
            raise e

    # header row
    headers=[[
        "Date","Product","Selling price","Cost price",
        "Quantity","Revenue","Profit","Image Preview","Image Link"
    ]]

    sheets.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="A1",
        valueInputOption="RAW",
        body={"values":headers}
    ).execute()

    return sheet_id


if not st.session_state.sheet_id:
    st.session_state.sheet_id=get_or_create_sheet()

SHEET_ID=st.session_state.sheet_id

# ---------------- IMAGE UPLOAD ----------------
def upload_image(path):

    try:
        file=drive.files().create(
            body={"name":os.path.basename(path),"parents":[PARENT_FOLDER_ID]},
            media_body=MediaFileUpload(path),
            fields="id"
        ).execute()
    except HttpError as e:
        if "storageQuotaExceeded" in str(e):
            st.error("Drive full — cannot upload image.")
            return None
        else:
            raise e

    file_id=file["id"]

    drive.permissions().create(
        fileId=file_id,
        body={"role":"reader","type":"anyone"}
    ).execute()

    return f"https://drive.google.com/uc?id={file_id}"

# ---------------- UI ----------------
st.title("📦 Product Recorder")

tab1,tab2 = st.tabs(["Add Product","Records"])

# ---------------- ADD PRODUCT ----------------
with tab1:

    img = st.camera_input("Take photo")
    name = st.text_input("Product name")
    price = st.number_input("Selling price",0.0)
    cost = st.number_input("Cost price",0.0)
    qty = st.number_input("Quantity",1)

    revenue = price*qty
    profit = (price-cost)*qty

    st.info(f"Revenue: {revenue}")
    st.info(f"Profit: {profit}")

    if st.button("Save"):

        if not img or not name:
            st.warning("Add image and name")
            st.stop()

        path=f"{int(time.time())}.png"
        with open(path,"wb") as f:
            f.write(img.getbuffer())

        link=upload_image(path)

        os.remove(path)

        if not link:
            st.stop()

        row=[[
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            name,price,cost,qty,revenue,profit,
            f'=IMAGE("{link}")',
            f'=HYPERLINK("{link}","View")'
        ]]

        sheets.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range="A:I",
            valueInputOption="USER_ENTERED",
            body={"values":row}
        ).execute()

        st.success("Saved")

# ---------------- VIEW DATA ----------------
with tab2:

    data=sheets.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="A:I"
    ).execute().get("values",[])

    if len(data)<=1:
        st.info("No records yet")
    else:
        df=pd.DataFrame(data[1:],columns=data[0])

        for c in ["Selling price","Cost price","Quantity","Revenue","Profit"]:
            df[c]=pd.to_numeric(df[c],errors="coerce").fillna(0)

        st.dataframe(df,use_container_width=True)
        st.success(f"Total Revenue: {df['Revenue'].sum()}")
        st.success(f"Total Profit: {df['Profit'].sum()}")
