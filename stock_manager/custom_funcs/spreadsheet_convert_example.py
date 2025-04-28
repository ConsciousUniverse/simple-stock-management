import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.workbook.workbook import Workbook as OpenpyxlWorkbook


def _df_from_wb(wb: OpenpyxlWorkbook, sheet_name: str) -> pd.DataFrame:
    """
    Given an openpyxl Workbook `wb` and a sheet name,
    read that sheet into a pandas DataFrame.
    """
    ws = wb[sheet_name]
    rows = list(ws.values)
    header, *data = rows
    return pd.DataFrame(data, columns=header)


def convert_excel(workbook: OpenpyxlWorkbook) -> OpenpyxlWorkbook:
    """
    Reads defined Worksheets from a passe-in openpyxl Workbook, and maps the sheets and fields to the correct format for the system to parse and submit to the database.
    Output MUST yield a Workbook (type OpenpyxlWorkbook) with the following:
        - One or both Worksheets named: 'Warehouse Stock' and 'Shop Stock'
        - If 'Warehouse Stock' Worksheet, must have headers "SKU", "Description", "Retail Price", "Quantity".
        - If 'Shop Stock' Worksheet, must have headers "Shop User", "SKU", "Description", "Retail Price", "Quantity".
    If the `wh_locs` list (defined below) is empty, only 'Shop Stock' is created.
    If `shop_users` list is empty, only 'Warehouse Stock' is created.
    Otherwise, both sheets are created.
    """
    # Load source sheets into DataFrames
    df_input = _df_from_wb(workbook, "Example workbook name")
    # Column definitions
    sku_col = "product code"
    desc_col = "product desc"
    price_col = "price"
    # Leave shop_users list empty if only uploaded Warehouse Stock.
    shop_users = ["London", "Paris", "Rome", "New York", "Amsterdam"]
    # Note, multiple warehouses are combined in the output file, as system presently only handles ONE warehouse. Leave empty list if only uploading Shop Stock.
    wh_locs = ["Inverness", "Aberdeen"]
    shop_users_map = {
        "London": "shop.london",
        "Paris": "shop.paris",
        "Rome": "shop.rome",
        "New York": "shop.ny",
        "Amsterdam": "shop.amsterdam",
    }
     # Drop rows without SKU
    if sku_col in df_input.columns:
        df_input = df_input[df_input[sku_col].notna() & (df_input[sku_col] != "")]

    # Cast and fill numeric columns
    for col in shop_users + wh_locs + [price_col]:
        if col in df_input.columns:
            df_input[col] = pd.to_numeric(df_input[col], errors="coerce").fillna(0)

    # Prepare Shop Stock if configured
    shop_df = None
    if shop_users:
        shop_cols = [c for c in shop_users if c in df_input.columns]
        if shop_cols:
            # Melt into shop-level rows
            shop_df = (
                df_input[[sku_col, desc_col, price_col] + shop_cols]
                .melt(
                    id_vars=[sku_col, desc_col, price_col],
                    value_vars=shop_cols,
                    var_name="Shop User",
                    value_name="Quantity",
                )
                # Map shop codes to final Shop User values
                .assign(
                    **{'Shop User': lambda df: df['Shop User']
                        .map(shop_users_map)
                        .fillna(df['Shop User'])}
                )
                # Ensure quantities are int
                .assign(
                    Quantity=lambda df: pd.to_numeric(
                        df['Quantity'], errors='coerce'
                    ).fillna(0).astype(int)
                )
                # Drop zero quantities
                .loc[lambda df: df['Quantity'] > 0]
                # Rename and reorder columns
                .rename(
                    columns={
                        sku_col:   'SKU',
                        desc_col:  'Description',
                        price_col: 'Retail Price'
                    }
                )[['Shop User', 'SKU', 'Description', 'Retail Price', 'Quantity']]
            )

    # Prepare Warehouse Stock if configured
    warehouse_df = None
    if wh_locs:
        wh_cols = [c for c in wh_locs if c in df_input.columns]
        if wh_cols:
            warehouse_main = (
                df_input[[sku_col, desc_col, price_col] + wh_cols]
                .assign(
                    Quantity=lambda df: df[wh_cols].sum(axis=1).astype(int)
                )
                .rename(columns={
                    sku_col:   'SKU',
                    desc_col:  'Description',
                    price_col: 'Retail Price'
                })[['SKU','Description','Retail Price','Quantity']]
            )
            # Aggregate duplicates
            warehouse_df = (
                warehouse_main
                .groupby(['SKU','Description','Retail Price'], as_index=False)
                .agg({'Quantity':'sum'})
            )

    # Create output workbook
    wb_out = Workbook()
    ws_active = wb_out.active

    # Write Warehouse Stock if exists
    if warehouse_df is not None:
        ws_active.title = "Warehouse Stock"
        for row in dataframe_to_rows(warehouse_df, index=False, header=True):
            ws_active.append(row)
    # If no warehouse sheet but shop exists, rename active to shop
    elif shop_df is not None:
        ws_active.title = "Shop Stock"
        for row in dataframe_to_rows(shop_df, index=False, header=True):
            ws_active.append(row)

    # Write Shop Stock as second sheet if both exist
    if warehouse_df is not None and shop_df is not None:
        ws_shop = wb_out.create_sheet("Shop Stock")
        for row in dataframe_to_rows(shop_df, index=False, header=True):
            ws_shop.append(row)

    return wb_out
