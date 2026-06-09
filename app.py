import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="LIDOM Hitter Projection Grader", layout="wide")

st.title("LIDOM Hitter Projection Grader")
st.caption("Upload a hitter CSV and grade players based on traits that may translate to LIDOM performance.")

# ----------------------------
# Helpers
# ----------------------------
def normalize_name(x):
    return str(x).strip().lower().replace(" ", "").replace("_", "").replace("-", "").replace("/", "")

def find_col(columns, candidates):
    normalized = {normalize_name(c): c for c in columns}
    for cand in candidates:
        key = normalize_name(cand)
        if key in normalized:
            return normalized[key]
    return None

def safe_numeric(series):
    if series is None:
        return np.nan
    s = series.astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce")

def maybe_percent(series):
    s = safe_numeric(series)
    # If values look like 0.65, keep them.
    # If values look like 65, convert to 0.65.
    if s.dropna().empty:
        return s
    if s.dropna().median() > 1.5:
        return s / 100
    return s

def percentile_score(series, higher_is_better=True):
    s = pd.to_numeric(series, errors="coerce")
    if s.notna().sum() <= 1:
        return pd.Series(np.full(len(s), 50.0), index=s.index)
    ranks = s.rank(pct=True, method="average") * 100
    if not higher_is_better:
        ranks = 100 - ranks
    return ranks.fillna(50)

def launch_angle_quality(avg_la, low, high):
    la = pd.to_numeric(avg_la, errors="coerce")
    midpoint = (low + high) / 2
    half_range = (high - low) / 2
    if half_range <= 0:
        half_range = 10
    # 100 near the center of the ideal range, declines as LA moves away.
    score = 100 - (abs(la - midpoint) / half_range * 50)
    return score.clip(0, 100).fillna(50)

def export_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="LIDOM Grades")
        workbook = writer.book
        worksheet = writer.sheets["LIDOM Grades"]
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAD3", "border": 1})
        percent_fmt = workbook.add_format({"num_format": "0.0%"})
        number_fmt = workbook.add_format({"num_format": "0.0"})
        grade_fmt = workbook.add_format({"bold": True, "num_format": "0.0"})
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            worksheet.set_column(col_num, col_num, max(12, min(28, len(str(value)) + 2)))
        for i, col in enumerate(df.columns):
            if "%" in col or "Rate" in col:
                worksheet.set_column(i, i, 13, percent_fmt)
            elif "Grade" in col and col != "Letter Grade":
                worksheet.set_column(i, i, 16, grade_fmt)
            elif col not in ["Player", "Letter Grade"]:
                worksheet.set_column(i, i, 13, number_fmt)
    return output.getvalue()

# ----------------------------
# Sidebar
# ----------------------------
st.sidebar.header("Grade Weights")

default_weights = {
    "Forward Velocity": 15,
    "Exit Velocity": 20,
    "Launch Angle": 15,
    "Hard Hit": 15,
    "Contact": 15,
    "Pull": 10,
    "OPS vs FB95": 10,
}

weights = {}
for metric, default in default_weights.items():
    weights[metric] = st.sidebar.slider(metric, 0, 40, default)

weight_sum = sum(weights.values())
if weight_sum == 0:
    st.sidebar.error("At least one weight must be above 0.")
    st.stop()

st.sidebar.header("Launch Angle Settings")
ideal_la_low = st.sidebar.number_input("Ideal LA lower bound", value=8.0)
ideal_la_high = st.sidebar.number_input("Ideal LA upper bound", value=28.0)

uploaded = st.file_uploader("Upload hitter CSV", type=["csv"])

if uploaded is None:
    st.info("Upload your hitter CSV to begin.")
    st.markdown("""
### Expected columns
The app will try to auto-detect these, and you can manually correct them:

- Player
- Forward Velocity
- Exit Velocity
- Launch Angle
- OPS vs FB95
- Contact%
- Hard Hit%
- Pull%
""")
    st.stop()

df = pd.read_csv(uploaded)
df.columns = [str(c).strip() for c in df.columns]

st.subheader("Column Mapping")

cols = ["-- None --"] + list(df.columns)

auto = {
    "player": find_col(df.columns, ["playerFullName", "Player", "Batter", "Hitter", "Hitter Name", "Batter Name"]),
    "forward_velocity": find_col(df.columns, ["ForwVel", "Forward Velocity", "ForwardVelocity", "FV"]),
    "exit_velocity": find_col(df.columns, ["ExitVel", "Exit Velocity", "ExitVelocity", "EV", "Avg Exit Velocity"]),
    "launch_angle": find_col(df.columns, ["LaunchAng", "Launch Angle", "LaunchAngle", "LA", "Avg Launch Angle"]),
    "ops_fb95": find_col(df.columns, ["OPS vs FB95", "OPSvsFB95", "OPS vs 95+", "OPS vs FB 95", "OPS v FB95"]),
    "contact": find_col(df.columns, ["Contact%", "Contact", "Contact Rate"]),
    "hard_hit": find_col(df.columns, ["Hard Hit%", "HardHit%", "Hard Hit", "HardHit", "Hard Hit Rate"]),
    "pull": find_col(df.columns, ["Pull%", "Pull", "Pull Rate"]),
}

def select_col(label, key):
    default = auto.get(key)
    index = cols.index(default) if default in cols else 0
    choice = st.selectbox(label, cols, index=index, key=key)
    return None if choice == "-- None --" else choice

c1, c2 = st.columns(2)

with c1:
    player_col = select_col("Player column", "player")
    fv_col = select_col("Forward Velocity column", "forward_velocity")
    ev_col = select_col("Exit Velocity column", "exit_velocity")
    la_col = select_col("Launch Angle column", "launch_angle")

with c2:
    ops_fb95_col = select_col("OPS vs FB95 column", "ops_fb95")
    contact_col = select_col("Contact column", "contact")
    hard_hit_col = select_col("Hard Hit column", "hard_hit")
    pull_col = select_col("Pull column", "pull")

if not player_col:
    st.error("Please select a player column.")
    st.stop()

required_for_grade = {
    "Forward Velocity": fv_col,
    "Exit Velocity": ev_col,
    "Launch Angle": la_col,
    "OPS vs FB95": ops_fb95_col,
    "Contact": contact_col,
    "Hard Hit": hard_hit_col,
    "Pull": pull_col,
}

missing = [k for k, v in required_for_grade.items() if v is None]
if missing:
    st.warning("Missing columns will be treated as neutral 50 scores: " + ", ".join(missing))

# ----------------------------
# Build player table
# ----------------------------
work = pd.DataFrame()
work["Player"] = df[player_col].astype(str)

if fv_col:
    work["Forward Velocity"] = safe_numeric(df[fv_col])
else:
    work["Forward Velocity"] = np.nan

if ev_col:
    work["Exit Velocity"] = safe_numeric(df[ev_col])
else:
    work["Exit Velocity"] = np.nan

if la_col:
    work["Launch Angle"] = safe_numeric(df[la_col])
else:
    work["Launch Angle"] = np.nan

if ops_fb95_col:
    work["OPS vs FB95"] = safe_numeric(df[ops_fb95_col])
else:
    work["OPS vs FB95"] = np.nan

if contact_col:
    work["Contact"] = maybe_percent(df[contact_col])
else:
    work["Contact"] = np.nan

if hard_hit_col:
    work["Hard Hit"] = maybe_percent(df[hard_hit_col])
else:
    work["Hard Hit"] = np.nan

if pull_col:
    work["Pull"] = maybe_percent(df[pull_col])
else:
    work["Pull"] = np.nan

# If player appears multiple times, average the available metrics.
summary = work.groupby("Player", dropna=False).agg({
    "Forward Velocity": "mean",
    "Exit Velocity": "mean",
    "Launch Angle": "mean",
    "OPS vs FB95": "mean",
    "Contact": "mean",
    "Hard Hit": "mean",
    "Pull": "mean",
}).reset_index()

# ----------------------------
# Scores
# ----------------------------
scores = pd.DataFrame({"Player": summary["Player"]})
scores["Forward Velocity Score"] = percentile_score(summary["Forward Velocity"])
scores["Exit Velocity Score"] = percentile_score(summary["Exit Velocity"])
scores["Launch Angle Score"] = launch_angle_quality(summary["Launch Angle"], ideal_la_low, ideal_la_high)
scores["Hard Hit Score"] = percentile_score(summary["Hard Hit"])
scores["Contact Score"] = percentile_score(summary["Contact"])
scores["Pull Score"] = percentile_score(summary["Pull"])
scores["OPS vs FB95 Score"] = percentile_score(summary["OPS vs FB95"])

for metric, col in {
    "Forward Velocity": "Forward Velocity Score",
    "Exit Velocity": "Exit Velocity Score",
    "Launch Angle": "Launch Angle Score",
    "Hard Hit": "Hard Hit Score",
    "Contact": "Contact Score",
    "Pull": "Pull Score",
    "OPS vs FB95": "OPS vs FB95 Score",
}.items():
    if required_for_grade[metric] is None:
        scores[col] = 50.0

final_score = pd.Series(0.0, index=summary.index)
weight_map = {
    "Forward Velocity": "Forward Velocity Score",
    "Exit Velocity": "Exit Velocity Score",
    "Launch Angle": "Launch Angle Score",
    "Hard Hit": "Hard Hit Score",
    "Contact": "Contact Score",
    "Pull": "Pull Score",
    "OPS vs FB95": "OPS vs FB95 Score",
}

for metric, score_col in weight_map.items():
    final_score += scores[score_col] * (weights[metric] / weight_sum)

summary["LIDOM Projection Grade"] = final_score.round(1)

def letter_grade(x):
    if pd.isna(x):
        return ""
    if x >= 90:
        return "A+"
    if x >= 85:
        return "A"
    if x >= 80:
        return "A-"
    if x >= 75:
        return "B+"
    if x >= 70:
        return "B"
    if x >= 65:
        return "B-"
    if x >= 60:
        return "C+"
    if x >= 55:
        return "C"
    return "D"

summary["Letter Grade"] = summary["LIDOM Projection Grade"].apply(letter_grade)

out = summary.merge(scores, on="Player", how="left")
out = out.sort_values("LIDOM Projection Grade", ascending=False)

# Format display copy
display = out.copy()
for col in ["Contact", "Hard Hit", "Pull"]:
    if col in display.columns:
        display[col] = display[col].apply(lambda x: "" if pd.isna(x) else f"{x:.1%}")

st.subheader("LIDOM Projection Leaderboard")
st.dataframe(display, use_container_width=True, hide_index=True)

top = out.head(10)
if len(top) > 0:
    st.subheader("Top 10")
    chart_df = top[["Player", "LIDOM Projection Grade"]].set_index("Player")
    st.bar_chart(chart_df)

st.subheader("Model Notes")
st.markdown("""
- The grade is percentile-based inside the uploaded CSV.
- Higher Forward Velocity, Exit Velocity, Hard Hit, Contact, Pull, and OPS vs FB95 improve the grade.
- Launch Angle is scored by closeness to the ideal range selected in the sidebar.
- Missing columns are treated as neutral 50 scores.
""")

excel_data = export_excel(out)
st.download_button(
    label="Download Results as Excel",
    data=excel_data,
    file_name="lidom_projection_grades.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

csv_data = out.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Download Results as CSV",
    data=csv_data,
    file_name="lidom_projection_grades.csv",
    mime="text/csv"
)
