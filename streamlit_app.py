import streamlit as st
import pandas as pd
import requests

# ---------- AUTHENTICATION ----------
api_key = st.secrets["HOLDED_API_KEY"]
PASSCODE = st.secrets["STREAMLIT_PASSCODE"]

# Require login passcode
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    user_input = st.text_input("🔐 Enter Passcode to Access", type="password")
    if user_input == PASSCODE:
        st.session_state.authenticated = True
        st.rerun()
    elif user_input:
        st.error("Incorrect passcode.")
    st.stop()

# ---------- FUNCTION TO FETCH AND PROCESS DATA ----------
def generate_units_table(doc_nums_to_include):
    url = "https://api.holded.com/api/invoicing/v1/documents/salesorder"

    headers = {
        "accept": "application/json",
        "key": api_key
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"API Error: {response.status_code} - {response.text}")
        
    data = response.json()
    orders_df = pd.DataFrame(data)

    filtered_orders = orders_df[orders_df['docNumber'].isin(doc_nums_to_include)]

    records = []
    for _, order in filtered_orders.iterrows():
        docnum = order['docNumber']
        for item in order.get('products', []):
            records.append({
                'SKU': item.get('sku', ''),
                'Product': item.get('name', ''),
                'Quantity': item.get('units', 0),
                'Order': docnum
            })

    df = pd.DataFrame(records)

    if df.empty:
        return pd.DataFrame(columns=["SKU", "Product", "Total"] + doc_nums_to_include)

    pivot = df.pivot_table(index=["SKU", "Product"], 
                           columns="Order", 
                           values="Quantity", 
                           aggfunc="sum", 
                           fill_value=0)

    pivot["Total"] = pivot.sum(axis=1)

    ordered_columns = ["Total"] + [col for col in doc_nums_to_include if col in pivot.columns]
    pivot = pivot[ordered_columns]

    pivot.reset_index(inplace=True)
    return pivot

# ---------- STREAMLIT UI ----------
st.set_page_config(page_title="Units Per Order Viewer", layout="wide")
st.title("📦 Units Per Order Report")

st.markdown("""
Enter one or more **Sales Order Document Numbers** (e.g., Wix250196, SO250066).  
The app will fetch product SKUs, names, and quantities from Holded, displaying totals and per-order breakdown.
""")

doc_numbers = st.text_input("Document Numbers (comma-separated):", placeholder="e.g. Wix250196, SO250066")

if st.button("Generate Report") or doc_numbers:
    doc_list = [doc.strip() for doc in doc_numbers.split(",") if doc.strip()]

    if not doc_list:
        st.warning("Please enter at least one valid document number.")
    else:
        try:
            df_result = generate_units_table(doc_list)
            if df_result.empty:
                st.warning("No products found for the given document numbers.")
            else:
                st.success("Report generated successfully!")
                st.dataframe(df_result, use_container_width=True)
        except Exception as e:
            st.error(f"An error occurred while fetching data: {e}")
