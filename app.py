import streamlit as st
import pandas as pd
import json
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# -------------------------
# CONFIG
# -------------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Put your JSON inside Streamlit secrets
SERVICE_ACCOUNT_INFO = dict(st.secrets["gcp_service_account"])

MASTER_SHEET_ID = st.secrets["sheet"]["id"]

# -------------------------
# AUTH
# -------------------------
creds = Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO,
    scopes=SCOPES
)

service = build("sheets", "v4", credentials=creds)

# -------------------------
# FUNCTIONS
# -------------------------

def get_or_create_user_sheet(email):
    spreadsheet = service.spreadsheets().get(
        spreadsheetId=MASTER_SHEET_ID
    ).execute()

    sheets = spreadsheet.get("sheets", [])
    titles = [s["properties"]["title"] for s in sheets]

    # if sheet already exists
    if email in titles:
        return email

    # create new sheet
    request = {
        "requests": [
            {
                "addSheet": {
                    "properties": {
                        "title": email
                    }
                }
            }
        ]
    }

    service.spreadsheets().batchUpdate(
        spreadsheetId=MASTER_SHEET_ID,
        body=request
    ).execute()

    return email


def write_row(sheet_name, row):
    body = {
        "values": [row]
    }

    service.spreadsheets().values().append(
        spreadsheetId=MASTER_SHEET_ID,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body=body
    ).execute()


# -------------------------
# UI
# -------------------------

st.title("Seller Recorder 📦")

if "user" not in st.session_state:
    st.session_state.user = None

# login
if st.session_state.user is None:
    email = st.text_input("Enter your email to start")

    if st.button("Login"):
        if email:
            st.session_state.user = email
            st.session_state.sheet = get_or_create_user_sheet(email)
            st.success("Logged in!")
            st.rerun()

# dashboard
else:
    st.success(f"Welcome {st.session_state.user}")

    product = st.text_input("Product name")
    price = st.number_input("Price", min_value=0.0)

    if st.button("Save"):
        write_row(
            st.session_state.sheet,
            [product, price]
        )
        st.success("Saved!")

    if st.button("Logout"):
        st.session_state.user = None
        st.rerun()
