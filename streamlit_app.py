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
    for url in urls.values():
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"API Error: {response.status_code} - {response.text}")
        df = pd.DataFrame(response.json())
        all_dfs.append(df)

    # Lowercase input list for comparison
    input_doc_nums_lc = [doc.strip().lower() for doc in doc_nums_to_include]

    # Track matches from API using original casing
    input_to_api_map = {}
    filtered_rows = []
    for df in all_dfs:
        df["docNumber_lower"] = df["docNumber"].str.lower()
        matches = df[df["docNumber_lower"].isin(input_doc_nums_lc)]

        for _, row in matches.iterrows():
            user_input = next((d for d in input_doc_nums_lc if d == row["docNumber_lower"]), None)
            if user_input and user_input not in input_to_api_map:
                input_to_api_map[user_input] = row["docNumber"]  # save original casing

        filtered_rows.append(matches)

    # Flatten product records
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

    # Determine which original-cased docNumbers we have
    api_doc_numbers = list(input_to_api_map.values())
    missing_docs = [doc for doc in doc_nums_to_include if doc.strip().lower() not in input_to_api_map]

    if df.empty:
        return pd.DataFrame(columns=["SKU", "Product", "Total"] + doc_nums_to_include)

    pivot = df.pivot_table(index=["SKU", "Product"],
                           columns="Order",
                           values="Quantity",
                           aggfunc="sum",
                           fill_value=0)

    # Add missing docNumber columns with 0s
    for doc in missing_docs:
        pivot[doc] = 0

    # Reorder columns: Total + in order of user input, but using API casing where available
    ordered_columns = []
    for doc in doc_nums_to_include:
        doc_lc = doc.strip().lower()
        corrected = input_to_api_map.get(doc_lc, doc)  # fallback to user input if not matched
        if corrected in pivot.columns:
            ordered_columns.append(corrected)

    pivot["Total"] = pivot[ordered_columns].sum(axis=1)
    pivot = pivot[["Total"] + ordered_columns]
    pivot.reset_index(inplace=True)
    return pivot

# ---------- STREAMLIT UI ----------
st.set_page_config(page_title="Informe de Unidades por DocNumber", layout="wide")
st.title("📦 Informe de Unidades por DocNumber")

st.markdown("""
Ingrese uno o más **números de documento** (por ejemplo: Wix250196, SO250066, PRO250070).  
La app mostrará los productos, SKUs y cantidades por documento, incluyendo un total.
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
                st.download_button("📥 Descargar CSV", data=csv, file_name="unidades_por_documento.csv", mime="text/csv")

        except Exception as e:
            st.error(f"Ocurrió un error al obtener los datos: {e}")
