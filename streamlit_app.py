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

# ---------- 🔄 EDIT: FETCH AND FILTER FUNCTION (MULTI-API) ----------
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
    for label, url in urls.items():
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"API Error ({label}): {response.status_code} - {response.text}")
        df = pd.DataFrame(response.json())
        df['source'] = label
        all_dfs.append(df)

    # Build input doc mapping (lowercased for matching)
    input_doc_nums_lc = [doc.strip().lower() for doc in doc_nums_to_include]

    # Gather all matching orders and keep original casing from the API
    filtered_rows = []
    found_docs = set()
    for df in all_dfs:
        df["docNumber_lower"] = df["docNumber"].str.lower()
        matches = df[df["docNumber_lower"].isin(input_doc_nums_lc)]
        filtered_rows.append(matches)
        found_docs.update(matches["docNumber"].tolist())  # use original casing

    # Flatten records
    records = []
    for df in filtered_rows:
        for _, order in df.iterrows():
            docnum_original = order["docNumber"]
            for item in order.get("products", []):
                records.append({
                    'SKU': item.get('sku', ''),
                    'Product': item.get('name', ''),
                    'Quantity': item.get('units', 1),
                    'Order': docnum_original
                })

    df = pd.DataFrame(records)

    # Determine original docNumbers (from API) for pivot headers
    all_order_columns = list(found_docs)
    missing_orders = [doc for doc in doc_nums_to_include if doc not in all_order_columns]

    if df.empty:
        return pd.DataFrame(columns=["SKU", "Product", "Total"] + doc_nums_to_include)

    pivot = df.pivot_table(index=["SKU", "Product"],
                           columns="Order",
                           values="Quantity",
                           aggfunc="sum",
                           fill_value=0)

    # Add missing orders with 0s
    for doc in missing_orders:
        pivot[doc] = 0

    # Final column ordering
    ordered_columns = [doc for doc in doc_nums_to_include if doc in pivot.columns]
    pivot["Total"] = pivot[ordered_columns].sum(axis=1)
    pivot = pivot[["Total"] + ordered_columns]

    pivot.reset_index(inplace=True)
    return pivot

# ---------- STREAMLIT UI ----------
st.set_page_config(page_title="Informe de Unidades por DocNumber", layout="wide")
st.title("📦 Informe de Unidades por Pedido")

st.markdown("""
Ingrese uno o más **números de documento** (por ejemplo: Wix250196, SO250066, PRO250070).  
La app mostrará los productos, SKUs y cantidades por pedido, incluyendo un total.
""")

doc_numbers = st.text_input("Números de documento (separados por comas):", placeholder="e.g. Wix250196, SO250066, PRO250070")

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

                # 🔄 Optional: download CSV
                csv = df_result.to_csv(index=False).encode("utf-8-sig")
                st.download_button("📥 Descargar CSV", data=csv, file_name="unidades_por_pedido.csv", mime="text/csv")

        except Exception as e:
            st.error(f"Ocurrió un error al obtener los datos: {e}")
