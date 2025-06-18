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

    # 🔠 Convert both input and dataset docNumbers to lowercase for case-insensitive match
    orders_df['docNumber'] = orders_df['docNumber'].str.lower()
    doc_nums_to_include = [doc.lower() for doc in doc_nums_to_include]

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
st.set_page_config(page_title="Informe de Unidades por Pedido", layout="wide")
st.title("📦 Informe de Unidades por Pedido")

st.markdown("""
Ingrese uno o más **números de documento de pedido** (por ejemplo: Wix250196, SO250066).  
La app mostrará los productos, SKUs y cantidades por pedido, incluyendo un total.
""")

doc_numbers = st.text_input("Números de documento (separados por comas):", placeholder="e.g. Wix250196, SO250066")

if st.button("Generar Informe") or doc_numbers:
    doc_list = [doc.strip() for doc in doc_numbers.split(",") if doc.strip()]

    if not doc_list:
        st.warning("Por favor, introduzca al menos un número de documento válido.")
    else:
        try:
            df_result = generate_units_table(doc_list)
            if df_result.empty:
                st.warning("No se encontraron productos para los documentos ingresados.")
            else:
                st.success("¡Informe generado con éxito!")
                st.dataframe(df_result, use_container_width=True)
        except Exception as e:
            st.error(f"Ocurrió un error al obtener los datos: {e}")

