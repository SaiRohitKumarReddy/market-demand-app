from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

import gspread
import pandas as pd
import plotly.express as px
import streamlit as st
from gspread import Worksheet
from gspread.exceptions import WorksheetNotFound


# -----------------------------------------------------------------------------
# App constants
# -----------------------------------------------------------------------------

PROFESSOR_SHEET = "professor"
STUDENT_SHEET = "student"
CONFIG_WORKSHEET = "simulation_config"

CONFIG_COLUMNS = [
    "product_name",
    "product_key",
    "min_price",
    "max_price",
    "number_of_people",
    "started_at",
]

BASE_RESPONSE_COLUMNS = ["submission_id", "submitted_at", "name"]
NUMBER_OF_UNITS = 4
ORDINALS = ("1st", "2nd", "3rd", "4th")


# -----------------------------------------------------------------------------
# Dynamic simulation configuration helpers
# -----------------------------------------------------------------------------

def product_to_key(product_name: str) -> str:
    """Convert a professor-entered product name into a safe Sheet column key."""
    key = re.sub(r"[^a-z0-9]+", "_", product_name.lower()).strip("_")
    return key or "product"


def get_price_columns(config: dict) -> list[str]:
    product_key = str(config["product_key"])
    return [f"{product_key}_{index}" for index in range(1, NUMBER_OF_UNITS + 1)]


def get_response_columns(config: dict) -> list[str]:
    return [*BASE_RESPONSE_COLUMNS, *get_price_columns(config)]


def get_price_labels(config: dict) -> list[str]:
    product_name = str(config["product_name"])
    return [
        f"How much are you willing to pay for the {ordinal} {product_name}?"
        for ordinal in ORDINALS
    ]


def get_progress_label(product_name: str) -> str:
    """Return a short progress label such as 'Scoop' from 'scoop of ice cream'."""
    first_part = product_name.split(" of ", 1)[0].strip()
    if not first_part or first_part[0].isdigit():
        return "Item"
    return first_part.title()


# -----------------------------------------------------------------------------
# Page configuration and styling
# -----------------------------------------------------------------------------

st.set_page_config(
    page_title="Market Demand",
    layout="wide",
)

st.markdown(
    """
    <style>
    /* Remove the clear-value X icon from number inputs. */
    svg[aria-label="Clear value"],
    svg[title="Clear value"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
        pointer-events: none !important;
    }

    div:has(> svg[aria-label="Clear value"]) {
        display: none !important;
        width: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    /* Hide Streamlit's default input instruction. */
    [data-testid="InputInstructions"] {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        width: 0 !important;
    }

    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

    html, body, [class*="css"], .stApp, .stMarkdown, .stDataFrame, button, input {
        font-family: 'Poppins', sans-serif !important;
    }

    :root {
        --bitsom-navy: #252A60;
        --bitsom-red: #B72E26;
        --bitsom-orange: #F58722;
        --bitsom-grey: #404041;
    }

    h1, h2, h3 {
        color: var(--bitsom-navy) !important;
    }

    hr {
        border-top: 2px solid var(--bitsom-orange) !important;
    }

    section[data-testid="stSidebar"] label {
        color: var(--bitsom-navy) !important;
    }

    [data-testid="stMetric"] {
        text-align: center !important;
    }

    [data-testid="stMetricValue"] {
        color: var(--bitsom-navy) !important;
    }

    [data-testid="stMetricLabel"] {
        color: var(--bitsom-grey) !important;
        font-size: 1.1rem !important;
        font-weight: 600 !important;
        justify-content: center !important;
    }

    button[kind="primary"], button[kind="primaryFormSubmit"] {
        background-color: var(--bitsom-navy) !important;
        border-color: var(--bitsom-navy) !important;
    }

    button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover {
        background-color: var(--bitsom-orange) !important;
        border-color: var(--bitsom-orange) !important;
    }

    table.bitsom-table {
        margin: 10px auto;
        border-collapse: collapse;
        font-size: 1.05rem;
    }

    table.bitsom-table th, table.bitsom-table td {
        padding: 10px 32px;
        text-align: center;
        border-bottom: 1px solid #E0E0E0;
        white-space: nowrap;
    }

    table.bitsom-table thead th {
        background-color: var(--bitsom-navy);
        color: #FFFFFF;
        font-weight: 600;
    }

    table.bitsom-table tbody tr:nth-child(even) {
        background-color: #F4F4F6;
    }

    button[kind="secondary"] {
        border-color: var(--bitsom-red) !important;
        color: var(--bitsom-red) !important;
    }

    button[kind="secondary"]:hover {
        background-color: var(--bitsom-red) !important;
        color: #FFFFFF !important;
        border-color: var(--bitsom-red) !important;
    }

    /* Large highlighted prompt shown above the name field. */
    .name-prompt {
        color: var(--bitsom-navy);
        background-color: #F4F4F6;
        border-left: 5px solid var(--bitsom-orange);
        border-radius: 6px;
        padding: 10px 14px;
        margin: 18px 0 8px 0;
        font-size: 1.35rem;
        font-weight: 700;
    }

    /* Larger price-question text. */
    .price-question {
        color: var(--bitsom-navy);
        font-size: 20px;
        font-weight: 600;
        line-height: 1.4;
        margin: 14px 0 8px 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Google Sheets helpers
# -----------------------------------------------------------------------------

@st.cache_resource
def get_google_worksheets() -> tuple[Worksheet, Worksheet, Worksheet]:
    """Connect once and return professor, student, and config worksheets."""
    credentials = dict(st.secrets["gcp_service_account"])
    client = gspread.service_account_from_dict(credentials)
    spreadsheet = client.open_by_key(str(st.secrets["SPREADSHEET_ID"]))

    professor_sheet = spreadsheet.worksheet(
        str(st.secrets["PROFESSOR_WORKSHEET"])
    )
    student_sheet = spreadsheet.worksheet(
        str(st.secrets["STUDENT_WORKSHEET"])
    )

    try:
        config_sheet = spreadsheet.worksheet(CONFIG_WORKSHEET)
    except WorksheetNotFound:
        config_sheet = spreadsheet.add_worksheet(
            title=CONFIG_WORKSHEET,
            rows=10,
            cols=len(CONFIG_COLUMNS),
        )

    config_header = config_sheet.row_values(1)
    if not config_header:
        config_sheet.update(
            range_name="A1:F1",
            values=[CONFIG_COLUMNS],
        )
    elif config_header != CONFIG_COLUMNS:
        raise ValueError(
            f"Worksheet '{CONFIG_WORKSHEET}' has incorrect column headings. "
            f"Expected: {', '.join(CONFIG_COLUMNS)}"
        )

    return professor_sheet, student_sheet, config_sheet


def get_worksheet(sheet_key: str) -> Worksheet:
    professor_sheet, student_sheet, _ = get_google_worksheets()

    if sheet_key == PROFESSOR_SHEET:
        return professor_sheet
    if sheet_key == STUDENT_SHEET:
        return student_sheet

    raise ValueError(f"Unknown worksheet key: {sheet_key}")


@st.cache_data(ttl=3, show_spinner=False)
def load_active_config() -> dict | None:
    """Read the professor-selected active simulation configuration."""
    _, _, config_sheet = get_google_worksheets()
    values = config_sheet.get_all_values()

    if len(values) <= 1:
        return None

    headers = values[0]
    row = values[1]
    padded_row = row + [""] * max(0, len(headers) - len(row))
    data = dict(zip(headers, padded_row[: len(headers)]))

    product_name = str(data.get("product_name", "")).strip()
    product_key = str(data.get("product_key", "")).strip()

    if not product_name or not product_key:
        return None

    try:
        min_price = int(data.get("min_price", ""))
        max_price = int(data.get("max_price", ""))
        number_of_people = int(data.get("number_of_people", ""))
    except (TypeError, ValueError):
        return None

    return {
        "product_name": product_name,
        "product_key": product_key,
        "min_price": min_price,
        "max_price": max_price,
        "number_of_people": number_of_people,
        "started_at": str(data.get("started_at", "")).strip(),
    }


def save_active_config(config: dict) -> None:
    """Persist the active simulation so every browser sees the same setup."""
    _, _, config_sheet = get_google_worksheets()
    config_sheet.clear()
    config_sheet.update(
        range_name="A1:F2",
        values=[
            CONFIG_COLUMNS,
            [config.get(column, "") for column in CONFIG_COLUMNS],
        ],
    )
    load_active_config.clear()


def clear_active_config() -> None:
    """Remove the active simulation configuration."""
    _, _, config_sheet = get_google_worksheets()
    config_sheet.clear()
    config_sheet.update(
        range_name="A1:F1",
        values=[CONFIG_COLUMNS],
    )
    load_active_config.clear()


def initialize_response_sheets(config: dict) -> None:
    """Start a new simulation and give both response sheets dynamic headings."""
    headers = get_response_columns(config)
    professor_sheet, student_sheet, _ = get_google_worksheets()

    for worksheet in (professor_sheet, student_sheet):
        worksheet.clear()
        worksheet.update(
            range_name="A1:G1",
            values=[headers],
        )

    read_responses.clear()


def worksheet_has_data(sheet_key: str) -> bool:
    """Return True when a response worksheet contains at least one data row."""
    values = get_worksheet(sheet_key).get_all_values()
    if len(values) <= 1:
        return False

    return any(
        any(str(value).strip() for value in row)
        for row in values[1:]
    )


def any_response_data_exists() -> bool:
    return worksheet_has_data(PROFESSOR_SHEET) or worksheet_has_data(STUDENT_SHEET)


def append_rows_safely(sheet_key: str, rows: list[dict], config: dict) -> None:
    """Append submissions using the dynamic product-specific Sheet headings."""
    response_columns = get_response_columns(config)
    worksheet = get_worksheet(sheet_key)
    first_row = worksheet.row_values(1)

    if not first_row:
        worksheet.update(
            range_name="A1:G1",
            values=[response_columns],
        )
    elif first_row != response_columns:
        raise ValueError(
            f"Worksheet '{worksheet.title}' has incorrect column headings. "
            f"Expected: {', '.join(response_columns)}"
        )

    values = [
        [row.get(column, "") for column in response_columns]
        for row in rows
    ]
    if values:
        worksheet.append_rows(values, value_input_option="RAW")
        read_responses.clear()


@st.cache_data(ttl=3, show_spinner=False)
def read_responses(sheet_key: str, product_key: str) -> pd.DataFrame:
    """Read response rows using the active product-specific headings."""
    price_columns = [
        f"{product_key}_{index}" for index in range(1, NUMBER_OF_UNITS + 1)
    ]
    response_columns = [*BASE_RESPONSE_COLUMNS, *price_columns]
    values = get_worksheet(sheet_key).get_all_values()

    if not values or len(values) <= 1:
        return pd.DataFrame(columns=response_columns)

    headers = values[0]
    if headers != response_columns:
        raise ValueError(
            f"Worksheet '{get_worksheet(sheet_key).title}' has incorrect column headings. "
            f"Expected: {', '.join(response_columns)}"
        )

    data_rows = []
    for row in values[1:]:
        if not any(str(value).strip() for value in row):
            continue

        padded_row = row + [""] * max(0, len(headers) - len(row))
        data_rows.append(dict(zip(headers, padded_row[: len(headers)])))

    if not data_rows:
        return pd.DataFrame(columns=response_columns)

    responses = pd.DataFrame(data_rows)
    for column in response_columns:
        if column not in responses.columns:
            responses[column] = ""

    return responses[response_columns]


def clear_worksheet_safely(sheet_key: str, config: dict | None) -> None:
    """Erase saved rows while retaining active product headings when applicable."""
    worksheet = get_worksheet(sheet_key)
    worksheet.clear()

    if config is not None:
        worksheet.update(
            range_name="A1:G1",
            values=[get_response_columns(config)],
        )

    read_responses.clear()


def clear_config_if_all_response_data_is_empty() -> bool:
    """
    Keep the active professor setup while either response sheet still has data.
    Once both response files are empty, remove the configuration and old headers.
    """
    if worksheet_has_data(PROFESSOR_SHEET) or worksheet_has_data(STUDENT_SHEET):
        return False

    clear_active_config()

    professor_sheet, student_sheet, _ = get_google_worksheets()
    professor_sheet.clear()
    student_sheet.clear()
    read_responses.clear()
    return True


# -----------------------------------------------------------------------------
# Validation and calculations
# -----------------------------------------------------------------------------

def validate_prices(prices: list[int | None], config: dict) -> str | None:
    """Validate completeness and the professor-selected whole-number range only."""
    if any(price is None for price in prices):
        return "Please enter all four price values."

    min_price = int(config["min_price"])
    max_price = int(config["max_price"])

    for price in prices:
        if isinstance(price, bool) or not isinstance(price, int):
            return "Every price must be a whole number."

        if price < min_price or price > max_price:
            return (
                f"Every price must be a whole number between "
                f"₹{min_price} and ₹{max_price}."
            )

    # No decreasing-price rule is applied. Any order is accepted.
    return None


def make_aggregate_table(responses: pd.DataFrame, config: dict) -> pd.DataFrame:
    table_columns = [
        "Price (₹)",
        "Quantity demanded",
        "Cumulative quantity demanded",
    ]

    if responses.empty:
        return pd.DataFrame(columns=table_columns)

    price_columns = get_price_columns(config)
    values = (
        responses[price_columns]
        .apply(pd.to_numeric, errors="coerce")
        .to_numpy()
        .flatten()
    )
    values = values[pd.notna(values)].astype(int)

    if len(values) == 0:
        return pd.DataFrame(columns=table_columns)

    unique_prices = sorted(set(values), reverse=True)
    return pd.DataFrame(
        {
            "Price (₹)": unique_prices,
            "Quantity demanded": [
                int((values == price).sum()) for price in unique_prices
            ],
            "Cumulative quantity demanded": [
                int((values >= price).sum()) for price in unique_prices
            ],
        }
    )


def render_aggregate_table(aggregate: pd.DataFrame) -> None:
    table_html = aggregate.to_html(index=False, border=0, classes="bitsom-table")
    st.markdown(table_html, unsafe_allow_html=True)


def show_aggregate_results(
    responses: pd.DataFrame,
    heading: str,
    response_label: str,
    config: dict,
) -> None:
    st.subheader(heading)

    if responses.empty:
        st.info("No responses have been submitted yet.")
        return

    aggregate = make_aggregate_table(responses, config)
    total_people = len(responses)
    product_name = str(config["product_name"])

    summary_table = pd.DataFrame(
        {
            response_label: [total_people],
            "Maximum quantity covered by this simulation": [
                total_people * NUMBER_OF_UNITS
            ],
        }
    )
    render_aggregate_table(summary_table)

    st.markdown("### Market demand data")
    render_aggregate_table(aggregate)

    st.markdown("### Market demand curve")

    # Use only real market-demand observations. No artificial quantity-zero
    # starting row is added, so the staircase begins at the first orange point.
    graph_data = aggregate[["Cumulative quantity demanded", "Price (₹)"]].copy()

    # Draw the staircase line with the requested vertical-then-horizontal shape.
    figure = px.line(
        graph_data,
        x="Cumulative quantity demanded",
        y="Price (₹)",
        markers=False,
        line_shape="vh",
    )
    figure.update_traces(
        line={"width": 3, "color": "#252A60"},
        hoverinfo="skip",
    )

    figure.add_scatter(
        x=aggregate["Cumulative quantity demanded"],
        y=aggregate["Price (₹)"],
        mode="markers",
        marker={"size": 9, "color": "#F58722"},
        name="Market demand",
        showlegend=False,
        hovertemplate=(
            "Cumulative quantity demanded: %{x}<br>"
            f"Price per {product_name}: ₹%{{y}}<extra></extra>"
        ),
    )

    minimum_quantity = int(aggregate["Cumulative quantity demanded"].min())
    maximum_quantity = int(aggregate["Cumulative quantity demanded"].max())
    minimum_price = int(aggregate["Price (₹)"].min())
    maximum_price = int(aggregate["Price (₹)"].max())
    price_padding = max(2, int((maximum_price - minimum_price) * 0.05))

    figure.update_layout(
        height=430,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font={"family": "Poppins, sans-serif", "color": "#404041"},
        xaxis={
            "range": [max(0.5, minimum_quantity - 0.5), maximum_quantity + 0.5],
            "tickmode": "array",
            "tickvals": list(range(minimum_quantity, maximum_quantity + 1)),
            "title": f"Cumulative quantity demanded ({product_name})",
        },
        yaxis={
            "range": [
                max(0, minimum_price - price_padding),
                maximum_price + price_padding,
            ],
            "title": f"Price per {product_name} (₹)",
        },
        hovermode="closest",
    )
    st.plotly_chart(figure, use_container_width=True)


def latest_professor_simulation(responses: pd.DataFrame) -> pd.DataFrame:
    if responses.empty:
        return responses

    latest_id = responses.iloc[-1]["submission_id"]
    return responses[responses["submission_id"] == latest_id].copy()


# -----------------------------------------------------------------------------
# Progressive input flow
# -----------------------------------------------------------------------------

def parse_price_input(
    raw_value: str,
    config: dict,
) -> tuple[int | None, str | None]:
    """Convert a typed price to an integer using the active professor range."""
    value = raw_value.strip()
    min_price = int(config["min_price"])
    max_price = int(config["max_price"])

    if not value:
        return None, None

    if value.startswith("-"):
        return None, (
            f"Negative values are not allowed. Enter a whole number "
            f"from {min_price} to {max_price}."
        )

    if "." in value:
        return None, (
            f"Decimal values are not allowed. Enter a whole number "
            f"from {min_price} to {max_price}."
        )

    if not value.isdigit():
        return None, (
            f"Only whole numbers are allowed. Enter a value "
            f"from {min_price} to {max_price}."
        )

    price = int(value)
    if price < min_price or price > max_price:
        return None, (
            f"Enter a whole number between ₹{min_price} and ₹{max_price}."
        )

    return price, None


def render_progressive_person(
    key_prefix: str,
    config: dict,
) -> tuple[str, list[int | None], bool]:
    """
    Display the name field first, then reveal one dynamic product question at a time.
    """
    st.markdown(
        '<div class="name-prompt">Enter name of the person</div>',
        unsafe_allow_html=True,
    )
    name = st.text_input(
        "Name",
        key=f"{key_prefix}_name",
        placeholder="Enter name and press Enter",
        label_visibility="collapsed",
    ).strip()

    prices: list[int | None] = [None] * NUMBER_OF_UNITS

    if not name:
        return name, prices, False

    price_labels = get_price_labels(config)
    progress_label = get_progress_label(str(config["product_name"]))
    min_price = int(config["min_price"])
    max_price = int(config["max_price"])

    price_column, _ = st.columns([1, 2])

    with price_column:
        for index, label in enumerate(price_labels, start=1):
            st.caption(f"{progress_label} {index} of {len(price_labels)}")

            st.markdown(
                f'<div class="price-question">{label}</div>',
                unsafe_allow_html=True,
            )

            raw_price = st.text_input(
                f"Price {index}",
                placeholder=(
                    f"Enter a whole number from {min_price} to {max_price} "
                    "and press Enter"
                ),
                key=f"{key_prefix}_price_{index}",
                label_visibility="collapsed",
            )
            price, validation_error = parse_price_input(raw_price, config)
            prices[index - 1] = price

            if validation_error:
                st.error(validation_error)
                return name, prices, False

            # Stop here until the current question has been answered correctly.
            if price is None:
                return name, prices, False

    return name, prices, True


# -----------------------------------------------------------------------------
# Session-state callbacks and save/reset actions
# -----------------------------------------------------------------------------

def toggle_results(state_key: str) -> None:
    st.session_state[state_key] = not st.session_state.get(state_key, False)


def toggle_reset_options() -> None:
    st.session_state["show_reset_options"] = not st.session_state.get(
        "show_reset_options",
        False,
    )


def start_simulation(
    product_name: str,
    min_price: int,
    max_price: int,
    number_of_people: int,
) -> str | None:
    """Validate professor setup, persist it, and create dynamic response headings."""
    product_name = product_name.strip()

    if not product_name:
        return "Please enter the product name."

    if min_price < 0 or max_price < 0:
        return "Minimum and maximum prices cannot be negative."

    if min_price > max_price:
        return "Minimum price cannot be greater than maximum price."

    if number_of_people not in (2, 3, 4):
        return "Please select 2, 3, or 4 people."

    if load_active_config() is not None:
        return "An active simulation already exists. Clear the existing data first."

    if any_response_data_exists():
        return (
            "Existing response data was found without an active configuration. "
            "Use Reset Mode to clear both response files before starting a new simulation."
        )

    config = {
        "product_name": product_name,
        "product_key": product_to_key(product_name),
        "min_price": int(min_price),
        "max_price": int(max_price),
        "number_of_people": int(number_of_people),
        "started_at": datetime.now(IST).replace(tzinfo=None).isoformat(timespec="seconds"),
    }

    save_active_config(config)
    initialize_response_sheets(config)

    st.session_state["professor_generation"] = (
        st.session_state.get("professor_generation", 0) + 1
    )
    st.session_state["student_generation"] = (
        st.session_state.get("student_generation", 0) + 1
    )
    st.session_state["professor_can_show_results"] = False
    st.session_state["student_can_show_results"] = False
    st.session_state["professor_results_visible"] = False
    st.session_state["student_results_visible"] = False
    return None


def save_professor_simulation(prefix: str, number_of_people: int) -> None:
    config = load_active_config()
    if config is None:
        st.session_state["professor_save_error"] = (
            "No active simulation is available. Start a simulation first."
        )
        return

    all_people: list[tuple[str, list[int]]] = []

    for person_index in range(1, number_of_people + 1):
        person_prefix = f"{prefix}_person_{person_index}"
        person_name = st.session_state.get(f"{person_prefix}_name", "").strip()
        raw_prices = [
            st.session_state.get(f"{person_prefix}_price_{price_index}", "")
            for price_index in range(1, NUMBER_OF_UNITS + 1)
        ]

        if not person_name:
            st.session_state["professor_save_error"] = "Please enter a name."
            return

        prices: list[int] = []
        for raw_price in raw_prices:
            price, input_error = parse_price_input(str(raw_price), config)
            if input_error or price is None:
                st.session_state["professor_save_error"] = (
                    f"{person_name}: "
                    f"{input_error or 'Please enter all four price values.'}"
                )
                return
            prices.append(price)

        validation_error = validate_prices(prices, config)
        if validation_error:
            st.session_state["professor_save_error"] = (
                f"{person_name}: {validation_error}"
            )
            return

        all_people.append((person_name, prices))

    simulation_id = f"prof-{uuid.uuid4().hex}"
    submitted_at = datetime.now(IST).replace(tzinfo=None).isoformat(timespec="seconds")
    price_columns = get_price_columns(config)

    rows = [
        {
            "submission_id": simulation_id,
            "submitted_at": submitted_at,
            "name": person_name,
            **dict(zip(price_columns, prices)),
        }
        for person_name, prices in all_people
    ]

    append_rows_safely(PROFESSOR_SHEET, rows, config)
    st.session_state["professor_success_message"] = (
        "Professor simulation saved. Click Show Results to view the table and graph."
    )
    st.session_state["professor_can_show_results"] = True
    st.session_state["professor_results_visible"] = False
    st.session_state["professor_generation"] = (
        st.session_state.get("professor_generation", 0) + 1
    )


def save_student_submission(prefix: str) -> None:
    config = load_active_config()
    if config is None:
        st.session_state["student_save_error"] = (
            "No active simulation is available."
        )
        return

    student_name = st.session_state.get(f"{prefix}_name", "").strip()
    raw_prices = [
        st.session_state.get(f"{prefix}_price_{price_index}", "")
        for price_index in range(1, NUMBER_OF_UNITS + 1)
    ]

    if not student_name:
        st.session_state["student_save_error"] = "Please enter your name."
        return

    prices: list[int] = []
    for raw_price in raw_prices:
        price, input_error = parse_price_input(str(raw_price), config)
        if input_error or price is None:
            st.session_state["student_save_error"] = (
                input_error or "Please enter all four price values."
            )
            return
        prices.append(price)

    validation_error = validate_prices(prices, config)
    if validation_error:
        st.session_state["student_save_error"] = validation_error
        return

    price_columns = get_price_columns(config)
    append_rows_safely(
        STUDENT_SHEET,
        [
            {
                "submission_id": f"student-{uuid.uuid4().hex}",
                "submitted_at": datetime.now(IST).replace(tzinfo=None).isoformat(timespec="seconds"),
                "name": student_name,
                **dict(zip(price_columns, prices)),
            }
        ],
        config,
    )

    st.session_state["student_success_message"] = (
        "Your response has been saved. Click Show Results to view the table and graph."
    )
    st.session_state["student_can_show_results"] = True
    st.session_state["student_results_visible"] = False
    st.session_state["student_generation"] = (
        st.session_state.get("student_generation", 0) + 1
    )


def reset_selected_file() -> None:
    selected_file = st.session_state.get("reset_file_choice", "Professor file")
    config = load_active_config()

    if selected_file == "Professor file":
        clear_worksheet_safely(PROFESSOR_SHEET, config)
        st.session_state["professor_generation"] = (
            st.session_state.get("professor_generation", 0) + 1
        )
        st.session_state["professor_results_visible"] = False
        st.session_state["professor_can_show_results"] = False
        base_message = (
            "Professor file has been reset. The saved professor responses, "
            "table, graph, and current Professor Mode inputs were cleared."
        )
    else:
        clear_worksheet_safely(STUDENT_SHEET, config)
        st.session_state["student_generation"] = (
            st.session_state.get("student_generation", 0) + 1
        )
        st.session_state["student_results_visible"] = False
        st.session_state["student_can_show_results"] = False
        base_message = (
            "Student file has been reset. All saved student responses, "
            "the student table, and the student graph were cleared."
        )

    configuration_cleared = clear_config_if_all_response_data_is_empty()
    if configuration_cleared:
        base_message += (
            " Both response files are now empty, so the active product and price "
            "configuration was also cleared."
        )
        st.session_state["professor_generation"] = (
            st.session_state.get("professor_generation", 0) + 1
        )
        st.session_state["student_generation"] = (
            st.session_state.get("student_generation", 0) + 1
        )

    st.session_state["file_reset_message"] = base_message
    st.session_state["show_reset_options"] = False


# -----------------------------------------------------------------------------
# Live results fragments
# -----------------------------------------------------------------------------

@st.fragment(run_every="3s")
def live_professor_results() -> None:
    config = load_active_config()
    if config is None:
        st.info("No active simulation is available.")
        return

    responses = read_responses(PROFESSOR_SHEET, str(config["product_key"]))
    show_aggregate_results(
        responses,
        heading="Live Professor Simulation",
        response_label="Total people",
        config=config,
    )
    st.caption("This section checks for a new professor simulation every 3 seconds.")


@st.fragment(run_every="3s")
def live_student_results() -> None:
    config = load_active_config()
    if config is None:
        st.info("No active simulation is available.")
        return

    responses = read_responses(STUDENT_SHEET, str(config["product_key"]))
    show_aggregate_results(
        responses,
        heading="Live Student Simulation",
        response_label="Total submissions",
        config=config,
    )
    st.caption("This section checks for new student submissions every 3 seconds.")


# -----------------------------------------------------------------------------
# App modes
# -----------------------------------------------------------------------------

def professor_mode() -> None:
    header_col, reset_col = st.columns([3, 1])

    with header_col:
        st.header("Professor Mode")

    with reset_col:
        st.button(
            "Reset Mode",
            on_click=toggle_reset_options,
            use_container_width=True,
        )

    reset_message = st.session_state.pop("file_reset_message", None)
    if reset_message:
        st.success(reset_message)

    success_message = st.session_state.pop("professor_success_message", None)
    if success_message:
        st.success(success_message)

    save_error = st.session_state.pop("professor_save_error", None)
    if save_error:
        st.error(save_error)

    if st.session_state.get("show_reset_options", False):
        st.warning("Choose which saved response file you want to permanently reset.")

        st.radio(
            "Select file to reset",
            options=["Professor file", "Student file"],
            horizontal=True,
            key="reset_file_choice",
        )

        confirm_col, cancel_col = st.columns(2)

        with confirm_col:
            st.button(
                "Confirm Reset",
                type="primary",
                on_click=reset_selected_file,
                use_container_width=True,
            )

        with cancel_col:
            if st.button("Cancel", use_container_width=True):
                st.session_state["show_reset_options"] = False
                st.rerun()

    config = load_active_config()

    # No active simulation: professor enters the setup once.
    if config is None:
        if any_response_data_exists():
            st.error(
                "Existing Professor/Student response data was found, but there is "
                "no active simulation configuration. Use Reset Mode to clear both "
                "response files before starting a new simulation."
            )
            return

        st.subheader("Simulation Setup")

        with st.form("professor_simulation_setup"):
            setup_column, _ = st.columns([1, 2])

            with setup_column:
                product_name = st.text_input(
                    "Product name",
                    placeholder="Example: scoop of ice cream",
                )
                min_price = st.number_input(
                    "Minimum price (₹)",
                    min_value=0,
                    value=0,
                    step=1,
                )
                max_price = st.number_input(
                    "Maximum price (₹)",
                    min_value=0,
                    value=120,
                    step=1,
                )
                number_of_people = st.selectbox(
                    "Select number of people to start simulation",
                    options=[2, 3, 4],
                    index=0,
                )

                start_clicked = st.form_submit_button(
                    "Start Simulation",
                    type="primary",
                    use_container_width=True,
                )

        if start_clicked:
            start_error = start_simulation(
                product_name=product_name,
                min_price=int(min_price),
                max_price=int(max_price),
                number_of_people=int(number_of_people),
            )
            if start_error:
                st.error(start_error)
            else:
                st.rerun()

        return

    # Active simulation: setup is locked and the existing professor flow runs.
    product_name = str(config["product_name"])
    min_price = int(config["min_price"])
    max_price = int(config["max_price"])
    number_of_people = int(config["number_of_people"])

    st.caption(
        f"Active product: {product_name}  |  "
        f"Price range: ₹{min_price}–₹{max_price}  |  "
        f"People: {number_of_people}"
    )

    generation = st.session_state.get("professor_generation", 0)
    prefix = f"professor_{generation}"

    completed_people: list[tuple[str, list[int | None]]] = []

    for person_index in range(1, number_of_people + 1):
        person_name, prices, person_complete = render_progressive_person(
            key_prefix=f"{prefix}_person_{person_index}",
            config=config,
        )
        completed_people.append((person_name, prices))

        # The next person is not displayed until this person is complete.
        if not person_complete:
            break

    all_people_complete = (
        len(completed_people) == number_of_people
        and all(
            person_name and all(price is not None for price in prices)
            for person_name, prices in completed_people
        )
    )

    if all_people_complete:
        st.button(
            "Save simulation",
            type="primary",
            use_container_width=True,
            key=f"{prefix}_save_button",
            on_click=save_professor_simulation,
            args=(prefix, number_of_people),
        )

    if st.session_state.get("professor_can_show_results", False):
        st.divider()

        professor_results_visible = st.session_state.get(
            "professor_results_visible",
            False,
        )
        st.button(
            "Hide Results" if professor_results_visible else "Show Results",
            type="primary" if not professor_results_visible else "secondary",
            use_container_width=True,
            key="professor_results_button",
            on_click=toggle_results,
            args=("professor_results_visible",),
        )

        if st.session_state.get("professor_results_visible", False):
            live_professor_results()


def student_mode() -> None:
    st.header("Student Mode")

    config = load_active_config()
    if config is None:
        st.info(
            "No active simulation is available yet. Please wait for the professor "
            "to start a simulation."
        )
        return

    success_message = st.session_state.pop("student_success_message", None)
    if success_message:
        st.success(success_message)

    save_error = st.session_state.pop("student_save_error", None)
    if save_error:
        st.error(save_error)

    product_name = str(config["product_name"])
    st.write(
        f"Enter your willingness to pay for each additional {product_name}. "
        # "Your name and individual answers will not appear in the public results."
    )

    generation = st.session_state.get("student_generation", 0)
    prefix = f"student_{generation}"

    student_name, prices, response_complete = render_progressive_person(
        key_prefix=prefix,
        config=config,
    )

    if response_complete:
        st.button(
            "Submit response",
            type="primary",
            use_container_width=True,
            key=f"{prefix}_submit_button",
            on_click=save_student_submission,
            args=(prefix,),
        )

    if st.session_state.get("student_can_show_results", False):
        st.divider()

        student_results_visible = st.session_state.get(
            "student_results_visible",
            False,
        )
        st.button(
            "Hide Results" if student_results_visible else "Show Results",
            type="primary" if not student_results_visible else "secondary",
            use_container_width=True,
            key="student_results_button",
            on_click=toggle_results,
            args=("student_results_visible",),
        )

        if st.session_state.get("student_results_visible", False):
            live_student_results()


# -----------------------------------------------------------------------------
# Main app
# -----------------------------------------------------------------------------

active_config = load_active_config()

if active_config is not None:
    product_key = str(active_config["product_key"])

    if "professor_can_show_results" not in st.session_state:
        st.session_state["professor_can_show_results"] = not read_responses(
            PROFESSOR_SHEET,
            product_key,
        ).empty

    if "student_can_show_results" not in st.session_state:
        st.session_state["student_can_show_results"] = not read_responses(
            STUDENT_SHEET,
            product_key,
        ).empty
else:
    st.session_state["professor_can_show_results"] = False
    st.session_state["student_can_show_results"] = False

if "professor_results_visible" not in st.session_state:
    st.session_state["professor_results_visible"] = False

if "student_results_visible" not in st.session_state:
    st.session_state["student_results_visible"] = False

st.title("Market Demand")

selected_mode = st.sidebar.radio(
    "Choose a mode",
    options=["Professor Mode", "Student Mode"],
)

if selected_mode == "Professor Mode":
    professor_mode()
else:
    student_mode()
