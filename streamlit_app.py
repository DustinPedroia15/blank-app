import streamlit as st
import pandas as pd
import requests
import io

# ---------- AUTHENTICATION ----------
api_key = st.secrets["HOLDED_API_KEY"]
PASSCODE = st.secrets["STREAMLIT_PASSCODE"]

# Require login passcode
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    user_input = st.text_input("🔐Ingrese la contraseña", type="password")
    if user_input == PASSCODE:
        st.session_state.authenticated = True
        st.rerun()
    elif user_input:
        st.error("Incorrect passcode.")
    st.stop()

# ---------- Holded product stock helpers ----------

BASE_URL  = "https://api.holded.com/api/invoicing/v1/products"
HEADERS   = {"accept": "application/json", "key": api_key}
PAGE_SIZE = 100

@st.cache_data(ttl=25000, show_spinner=True)
def fetch_all_products():
    """Retrieve all products from Holded with simple pagination."""
    all_products = []
    page = 1

    while True:
        resp = requests.get(
            BASE_URL,
            headers=HEADERS,
            params={"page": page, "limit": PAGE_SIZE}
        )
        resp.raise_for_status()
        data = resp.json()
        chunk = data.get("data", data) if isinstance(data, dict) else data
        if not chunk:
            break
        all_products.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            break
        page += 1

    return all_products

@st.cache_data(ttl=25000, show_spinner=True)
def build_sku_to_stock():
    """Return dict mapping SKU → current available stock."""
    sku_to_stock = {}
    for product in fetch_all_products():
        sku   = product.get("sku")
        stock = product.get("stock")
        if sku:
            sku_to_stock[sku] = stock
    return sku_to_stock

SKU_TO_STOCK = build_sku_to_stock()

# ---------- 🔄 FETCH AND FILTER FUNCTION (MULTI-API) ----------

def generate_units_table(doc_nums_to_include):
    headers = {
        "accept": "application/json",
        "key": api_key
    }

    urls = {
        "Estimate": "https://api.holded.com/api/invoicing/v1/documents/estimate",
        "Proforma": "https://api.holded.com/api/invoicing/v1/documents/proform",
        "SalesOrder": "https://api.holded.com/api/invoicing/v1/documents/salesorder"
    }

    all_dfs = []
    for url in urls.values():
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"API Error: {response.status_code} - {response.text}")
        df = pd.DataFrame(response.json())
        all_dfs.append(df)

    input_doc_nums_lc = [doc.strip().lower() for doc in doc_nums_to_include]

    input_to_api_map = {}
    filtered_rows = []
    for df in all_dfs:
        df["docNumber_lower"] = df["docNumber"].str.lower()
        matches = df[df["docNumber_lower"].isin(input_doc_nums_lc)]

        for _, row in matches.iterrows():
            user_input = next((d for d in input_doc_nums_lc if d == row["docNumber_lower"]), None)
            if user_input and user_input not in input_to_api_map:
                input_to_api_map[user_input] = row["docNumber"]

        filtered_rows.append(matches)

    records = []
    for df in filtered_rows:
        for _, order in df.iterrows():
            docnum = order["docNumber"]
            for item in order.get("products", []):
                records.append({
                    "SKU": item.get("sku", ""),
                    "Product": item.get("name", ""),
                    "Quantity": item.get("units", 1),
                    "Order": docnum
                })

    df = pd.DataFrame(records)
    api_doc_numbers = list(input_to_api_map.values())
    missing_docs = [doc for doc in doc_nums_to_include if doc.strip().lower() not in input_to_api_map]

    if df.empty:
        return pd.DataFrame(columns=["SKU", "Product", "Total"] + doc_nums_to_include)

    pivot = df.pivot_table(index=["SKU", "Product"],
                           columns="Order",
                           values="Quantity",
                           aggfunc="sum",
                           fill_value=0)

    for doc in missing_docs:
        pivot[doc] = 0

    ordered_columns = []
    for doc in doc_nums_to_include:
        doc_lc = doc.strip().lower()
        corrected = input_to_api_map.get(doc_lc, doc)
        if corrected in pivot.columns:
            ordered_columns.append(corrected)

    pivot["Total"] = pivot[ordered_columns].sum(axis=1)
    pivot = pivot[ordered_columns + ["Total"]]
    pivot.reset_index(inplace=True)

    # --- Fetch product data for stock values ---
    all_products = fetch_all_products()
    sku_to_stock = {}
    for product in all_products:
        sku = product.get("sku")
        stock = product.get("stock")
        if sku:
            sku_to_stock[sku] = stock

    # --- Add Stock Disponible column ---
    pivot["Stock Disponible"] = pivot["SKU"].map(sku_to_stock)
    pivot["Stock Disponible"] = pivot["Stock Disponible"] + pivot["Total"]

    
    # --- Add Diferencia column ---
    def calc_diferencia(row):
        diff = row["Stock Disponible"] - row["Total"]
        if diff < 0:
            return pd.Series([abs(diff), None])
        else:
            return pd.Series([None, diff])
    
    # Apply the function and create two new columns
    pivot[["Stock Falta", "Stock Adicional"]] = pivot.apply(calc_diferencia, axis=1)
    
    # Filter out rows where SKU is "0"
    #pivot = pivot[pivot["SKU"].astype(str).str.strip() != "0"]
    return pivot

# ---------- STREAMLIT UI ----------

st.set_page_config(page_title="Informe de Unidades por DocNumber", layout="wide")
st.title("📦 Informe de Unidades por DocNumber")

st.markdown("""
Ingrese uno o más **números de documento** de Presupuesto, Proforma, y Pedido (por ejemplo: Wix250196, SO250066, PRO250070).  
La app mostrará los productos, SKUs y cantidades por documento, incluyendo un total, el stock disponible y la diferencia.
""")
if st.button("🔄 Refresh Data"):
    st.cache_data.clear()
    
doc_numbers = st.text_input("Números de documento (separados por comas):", placeholder="e.g. Wix250196, SO250066, PRO250070")
    
if st.button("Generar Informe") or doc_numbers:
    doc_list = [doc.strip() for doc in doc_numbers.split(",") if doc.strip()]

    if not doc_list:
        st.warning("Por favor, introduzca al menos un número de documento válido.")
        st.stop()

    try:
        df_result = generate_units_table(doc_list)
        if df_result.empty:
            st.warning("No se encontraron productos para los documentos ingresados.")
        else:
            st.success("¡Informe generado con éxito!")
            st.dataframe(df_result, use_container_width=True)

          
            filename="unidades_por_documento.xlsx"
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_result.to_excel(writer, index=False, sheet_name='Sheet1')
            excel_buffer.seek(0)
                
                    # Download button
            st.download_button(
                label="📥 Download Excel",
                data=excel_buffer,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            
    except Exception as e:
        st.error(f"Ocurrió un error al obtener los datos: {e}")
