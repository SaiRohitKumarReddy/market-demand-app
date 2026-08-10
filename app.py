from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

import gspread
import pandas as pd
import plotly.express as px
import streamlit as st
from gspread import Worksheet


PRICE_COLUMNS = ["Laddo_1", "Laddo_2", "Laddo_3", "Laddo_4"]
RESPONSE_COLUMNS = ["submission_id", "submitted_at", *PRICE_COLUMNS]
PROFESSOR_SHEET = "professor"
STUDENT_SHEET = "student"

PRICE_LABELS = [
    "How much are you willing to pay for the 1st Laddo?",
    "How much are you willing to pay for the 2nd Laddo?",
    "How much are you willing to pay for the 3rd Laddo?",
    "How much are you willing to pay for the 4th Laddo?",
]


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
def get_google_worksheets() -> tuple[Worksheet, Worksheet]:
    """Connect once and return the professor and student worksheets."""
    credentials = dict(st.secrets["gcp_service_account"])
    client = gspread.service_account_from_dict(credentials)
    spreadsheet = client.open_by_key(str(st.secrets["SPREADSHEET_ID"]))

    professor_sheet = spreadsheet.worksheet(
        str(st.secrets["PROFESSOR_WORKSHEET"])
    )
    student_sheet = spreadsheet.worksheet(
        str(st.secrets["STUDENT_WORKSHEET"])
    )

    for worksheet in (professor_sheet, student_sheet):
        first_row = worksheet.row_values(1)
        if not first_row:
            worksheet.update(
                range_name="A1:G1",
                values=[RESPONSE_COLUMNS],
            )
        elif first_row != RESPONSE_COLUMNS:
            raise ValueError(
                f"Worksheet '{worksheet.title}' has incorrect column headings. "
                f"Expected: {', '.join(RESPONSE_COLUMNS)}"
            )

    return professor_sheet, student_sheet


def get_worksheet(sheet_key: str) -> Worksheet:
    professor_sheet, student_sheet = get_google_worksheets()

    if sheet_key == PROFESSOR_SHEET:
        return professor_sheet
    if sheet_key == STUDENT_SHEET:
        return student_sheet

    raise ValueError(f"Unknown worksheet key: {sheet_key}")


def append_rows_safely(sheet_key: str, rows: list[dict]) -> None:
    """Append submissions to the selected Google Sheet worksheet."""
    values = [
        [row.get(column, "") for column in RESPONSE_COLUMNS]
        for row in rows
    ]
    if values:
        get_worksheet(sheet_key).append_rows(values, value_input_option="RAW")
        read_responses.clear()


@st.cache_data(ttl=3, show_spinner=False)
def read_responses(sheet_key: str) -> pd.DataFrame:
    """Read worksheet rows into a DataFrame with the expected columns."""
    values = get_worksheet(sheet_key).get_all_values()

    if len(values) <= 1:
        return pd.DataFrame(columns=RESPONSE_COLUMNS)

    headers = values[0]
    data_rows = []

    for row in values[1:]:
        if not any(str(value).strip() for value in row):
            continue

        padded_row = row + [""] * max(0, len(headers) - len(row))
        data_rows.append(dict(zip(headers, padded_row[: len(headers)])))

    if not data_rows:
        return pd.DataFrame(columns=RESPONSE_COLUMNS)

    responses = pd.DataFrame(data_rows)
    for column in RESPONSE_COLUMNS:
        if column not in responses.columns:
            responses[column] = ""

    return responses[RESPONSE_COLUMNS]


def clear_worksheet_safely(sheet_key: str) -> None:
    """Erase saved rows while retaining the expected header row."""
    worksheet = get_worksheet(sheet_key)
    worksheet.clear()
    worksheet.update(
        range_name="A1:G1",
        values=[RESPONSE_COLUMNS],
    )
    read_responses.clear()


# -----------------------------------------------------------------------------
# Validation and calculations
# -----------------------------------------------------------------------------

def validate_prices(prices: list[int | None]) -> str | None:
    """Validate completeness and the ₹0-₹120 whole-number range only."""
    if any(price is None for price in prices):
        return "Please enter all four price values."

    for price in prices:
        if isinstance(price, bool) or not isinstance(price, int):
            return "Every price must be a whole number."

        if price < 0 or price > 120:
            return "Every price must be a whole number between ₹0 and ₹120."

    # No decreasing-price rule is applied. Any order is accepted.
    return None


def make_aggregate_table(responses: pd.DataFrame) -> pd.DataFrame:
    table_columns = [
        "Price (₹)",
        "Quantity demanded",
        "Cumulative quantity demanded",
    ]

    if responses.empty:
        return pd.DataFrame(columns=table_columns)

    values = (
        responses[PRICE_COLUMNS]
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
) -> None:
    st.subheader(heading)

    if responses.empty:
        st.info("No responses have been submitted yet.")
        return

    aggregate = make_aggregate_table(responses)
    total_people = len(responses)

    summary_table = pd.DataFrame(
        {
            response_label: [total_people],
            "Maximum quantity": [total_people * 4],
        }
    )
    render_aggregate_table(summary_table)

    st.markdown("### Market Demand Data")
    render_aggregate_table(aggregate)

    st.markdown("### Market Demand Curve")

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

    # Show orange markers only for actual market-demand observations, not for
    # the invisible quantity-zero starting row.
    figure.add_scatter(
        x=aggregate["Cumulative quantity demanded"],
        y=aggregate["Price (₹)"],
        mode="markers",
        marker={"size": 9, "color": "#F58722"},
        name="Market demand",
        showlegend=False,
        hovertemplate=(
            "Cumulative quantity demanded: %{x}<br>"
            "Price per Laddo: ₹%{y}<extra></extra>"
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
            # Start the visible axis at the first real cumulative quantity.
            # This removes the unused quantity-zero area and the extra first line.
            "range": [max(0.5, minimum_quantity - 0.5), maximum_quantity + 0.5],
            "tickmode": "array",
            "tickvals": list(range(minimum_quantity, maximum_quantity + 1)),
            "title": "Cumulative quantity of Laddo demanded",
        },
        yaxis={
            # Do not force the price axis down to zero.
            "range": [
                max(0, minimum_price - price_padding),
                maximum_price + price_padding,
            ],
            "title": "Price per Laddo (₹)",
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

def parse_price_input(raw_value: str) -> tuple[int | None, str | None]:
    """Convert a typed price to an integer and return a clear validation error."""
    value = raw_value.strip()

    if not value:
        return None, None

    if value.startswith("-"):
        return None, "Negative values are not allowed. Enter a whole number from 0 to 120."

    if "." in value:
        return None, "Decimal values are not allowed. Enter a whole number from 0 to 120."

    if not value.isdigit():
        return None, "Only whole numbers are allowed. Enter a value from 0 to 120."

    price = int(value)
    if price > 120:
        return None, "The maximum allowed price is ₹120."

    return price, None


def render_progressive_person(
    key_prefix: str,
) -> tuple[str, list[int | None], bool]:
    """
    Display the full-width name prompt and name field first, then reveal one
    compact price question at a time below it.
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

    prices: list[int | None] = [None, None, None, None]

    if not name:
        return name, prices, False

    price_column, _ = st.columns([1, 2])

    with price_column:
        for index, label in enumerate(PRICE_LABELS, start=1):

            st.markdown(
                f'<div class="price-question">{label}</div>',
                unsafe_allow_html=True,
            )

            raw_price = st.text_input(
                f"Price {index}",
                placeholder="Enter a whole number from 0 to 120 and press Enter",
                key=f"{key_prefix}_price_{index}",
                label_visibility="collapsed",
            )
            price, validation_error = parse_price_input(raw_price)
            prices[index - 1] = price

            if validation_error:
                st.error(validation_error)
                return name, prices, False

            # Stop here until the current question has been answered correctly.
            if price is None:
                return name, prices, False

    return name, prices, True


# -----------------------------------------------------------------------------
# Session-state callbacks
# -----------------------------------------------------------------------------

def toggle_results(state_key: str) -> None:
    st.session_state[state_key] = not st.session_state.get(state_key, False)


def toggle_reset_options() -> None:
    st.session_state["show_reset_options"] = not st.session_state.get(
        "show_reset_options",
        False,
    )


def save_professor_simulation(prefix: str, number_of_people: int) -> None:
    all_people: list[tuple[str, list[int]]] = []

    for person_index in range(1, number_of_people + 1):
        person_prefix = f"{prefix}_person_{person_index}"
        person_name = st.session_state.get(f"{person_prefix}_name", "").strip()
        raw_prices = [
            st.session_state.get(f"{person_prefix}_price_{price_index}", "")
            for price_index in range(1, 5)
        ]

        if not person_name:
            st.session_state["professor_save_error"] = "Please enter a name."
            return

        prices: list[int] = []
        for raw_price in raw_prices:
            price, input_error = parse_price_input(str(raw_price))
            if input_error or price is None:
                st.session_state["professor_save_error"] = (
                    f"{person_name}: {input_error or 'Please enter all four price values.'}"
                )
                return
            prices.append(price)

        validation_error = validate_prices(prices)
        if validation_error:
            st.session_state["professor_save_error"] = (
                f"{person_name}: {validation_error}"
            )
            return

        all_people.append((person_name, prices))

    simulation_id = f"prof-{uuid.uuid4().hex}"
    submitted_at = datetime.now(IST).replace(tzinfo=None).isoformat(timespec="seconds")

    rows = [
        {
            "submission_id": simulation_id,
            "submitted_at": submitted_at,
            "name": person_name,
            **dict(zip(PRICE_COLUMNS, prices)),
        }
        for person_name, prices in all_people
    ]

    append_rows_safely(PROFESSOR_SHEET, rows)
    st.session_state["professor_success_message"] = (
        "Professor simulation saved. Click Show Results to view the table and graph."
    )
    st.session_state["professor_can_show_results"] = True
    st.session_state["professor_results_visible"] = False
    st.session_state["professor_generation"] = (
        st.session_state.get("professor_generation", 0) + 1
    )


def save_student_submission(prefix: str) -> None:
    student_name = st.session_state.get(f"{prefix}_name", "").strip()
    raw_prices = [
        st.session_state.get(f"{prefix}_price_{price_index}", "")
        for price_index in range(1, 5)
    ]

    if not student_name:
        st.session_state["student_save_error"] = "Please enter your name."
        return

    prices: list[int] = []
    for raw_price in raw_prices:
        price, input_error = parse_price_input(str(raw_price))
        if input_error or price is None:
            st.session_state["student_save_error"] = (
                input_error or "Please enter all four price values."
            )
            return
        prices.append(price)

    validation_error = validate_prices(prices)
    if validation_error:
        st.session_state["student_save_error"] = validation_error
        return

    append_rows_safely(
        STUDENT_SHEET,
        [
            {
                "submission_id": f"student-{uuid.uuid4().hex}",
                "submitted_at": datetime.now(IST).replace(tzinfo=None).isoformat(timespec="seconds"),
                "name": student_name,
                **dict(zip(PRICE_COLUMNS, prices)),
            }
        ],
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

    if selected_file == "Professor file":
        clear_worksheet_safely(PROFESSOR_SHEET)
        st.session_state["professor_generation"] = (
            st.session_state.get("professor_generation", 0) + 1
        )
        st.session_state["professor_results_visible"] = False
        st.session_state["professor_can_show_results"] = False
        st.session_state["file_reset_message"] = (
            "Professor file has been reset. The saved professor responses, "
            "table, graph, and current Professor Mode inputs were cleared."
        )
    else:
        clear_worksheet_safely(STUDENT_SHEET)
        st.session_state["student_generation"] = (
            st.session_state.get("student_generation", 0) + 1
        )
        st.session_state["student_results_visible"] = False
        st.session_state["student_can_show_results"] = False
        st.session_state["file_reset_message"] = (
            "Student file has been reset. All saved student responses, "
            "the student table, and the student graph were cleared."
        )

    st.session_state["show_reset_options"] = False


# -----------------------------------------------------------------------------
# Live results fragments
# -----------------------------------------------------------------------------

@st.fragment(run_every="3s")
def live_professor_results() -> None:
    responses = read_responses(PROFESSOR_SHEET)
    show_aggregate_results(
        responses,
        heading="Professor Simulation",
        response_label="Total Submission",
    )
    st.caption("This section checks for a new professor simulation every 3 seconds.")


@st.fragment(run_every="3s")
def live_student_results() -> None:
    responses = read_responses(STUDENT_SHEET)
    show_aggregate_results(
        responses,
        heading="Student Simulation",
        response_label="Total submissions",
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

    #st.write(
     #   "Create people and demonstrate how individual willingness to pay "
      #  "forms a market demand curve. At each market price, the quantities "
       # "demanded by all individuals are added together to obtain the total "
        #"market quantity demanded."
    #)
   # st.caption(
    #    "Enter each answer and press Enter. The next question will appear below it."
    #)

    generation = st.session_state.get("professor_generation", 0)
    prefix = f"professor_{generation}"

    selection_column, _ = st.columns([1, 3])

    with selection_column:
        number_of_people = st.selectbox(
            "Select number of people to start simulation",
            options=[2, 3, 4],
            index=0,
            key=f"{prefix}_people_count",
        )

    completed_people: list[tuple[str, list[int | None]]] = []

    for person_index in range(1, number_of_people + 1):
        person_name, prices, person_complete = render_progressive_person(
            key_prefix=f"{prefix}_person_{person_index}",
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

    success_message = st.session_state.pop("student_success_message", None)
    if success_message:
        st.success(success_message)

    save_error = st.session_state.pop("student_save_error", None)
    if save_error:
        st.error(save_error)

    st.write(
        "Enter your willingness to pay for each additional Laddo. "
       # "Your name and individual answers will not appear in the public results."
    )
    #st.caption(
     #   "Enter each answer and press Enter. The next question will appear below it."
    #)

    generation = st.session_state.get("student_generation", 0)
    prefix = f"student_{generation}"

    student_name, prices, response_complete = render_progressive_person(
        key_prefix=prefix,
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

# A browser refresh creates a new Streamlit session and clears session_state.
# Rebuild result access from Google Sheets so users can still open saved
# results without entering another response.
if "professor_can_show_results" not in st.session_state:
    st.session_state["professor_can_show_results"] = not read_responses(
        PROFESSOR_SHEET
    ).empty

if "student_can_show_results" not in st.session_state:
    st.session_state["student_can_show_results"] = not read_responses(
        STUDENT_SHEET
    ).empty

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
