import streamlit as st
import pandas as pd
import numpy as np
import pydeck as pdk
import altair as alt
import os
from streamlit_push_notifications import send_push, send_alert
from datetime import datetime, timedelta

# =========================================================
# GRUNDKONFIGURATION
# =========================================================
st.set_page_config(
    page_title="Safety Heatmap Cockpit – Prototyp",
    layout="wide",
)

# =========================================================
# ROLLEN & LOGOS (aus LB-Prototyp)
# =========================================================

ROLE_LABEL = {
    "Leitstelle Stadtverkehr": "Leitstelle",
    "Polizei / Sicherheit": "Polizei",
    "Stadtverwaltung / Ordnungsamt": "Stadtverwaltung",
    "ÖV-Planung": "ÖV-Planung",
}

ROLE_LOGO = {
    "Leitstelle Stadtverkehr": "Verkehrsbetriebe.png",
    "Polizei / Sicherheit": "Polizei.png",
    "Stadtverwaltung / Ordnungsamt": "Stadtverwaltung.png",
    "ÖV-Planung": "Stadtplaner.png",
}

# =========================================================
# SESSION STATE INITIALISIEREN
# =========================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "role" not in st.session_state:
    st.session_state.role = None

if "data_timestamp" not in st.session_state:
    st.session_state.data_timestamp = None

if "data_cache" not in st.session_state:
    # dict: scenario für folgende Bodys (df_zones, df_trend, df_map, df_reports, df_fleet, df_battery)
    st.session_state.data_cache = {}
    
if "show_feedback" not in st.session_state:
    st.session_state.show_feedback = False

# =========================================================
# LOGIN-SCREEN (Layout angelehnt an LB)
# =========================================================
def render_login():
    st.markdown("# Safety Heatmap Cockpit – Login")

    col_login, col_info = st.columns([1, 1.3])

    with col_login:
        username = st.text_input("Benutzername")
        password = st.text_input("Passwort", type="password")
        rolle = st.selectbox(
            "Rolle",
            list(ROLE_LABEL.keys()),
        )

        if st.button("Anmelden"):
            if username and password:
                st.session_state.logged_in = True
                st.session_state.role = rolle
            else:
                st.error("Bitte Benutzername und Passwort eingeben.")

    with col_info:
        st.markdown("### Wofür ist dieses Cockpit?")
        st.markdown(
            """
            - **Lagebild in Echtzeit** für E-Scooter / Mikromobilität  
            - Visualisierung von **Hotspots** (Unfälle, Beschwerden, technische Störungen)  
            - Unterstützung von **Leitstelle, Polizei, Verwaltung und ÖV-Planung**  
            
            Melde dich an, um die für deine Rolle relevante Sicht zu erhalten.
            """
        )


# =========================================================
# ENTWEDER LOGIN ODER HAUPT-APP
# =========================================================
if not st.session_state.logged_in:
    render_login()
else:
    # =========================================================
    # NACH LOGIN: HEADER MIT ROLLE & LOGO (LB-Style)
    # =========================================================
    role = st.session_state.role
    role_label = ROLE_LABEL.get(role, "")
    logo_path = ROLE_LOGO.get(role, None)

    header_col_left, header_col_right = st.columns([4, 1])
    with header_col_left:
        st.markdown(
            f"## Safety Heatmap Cockpit – {role_label if role_label else 'Übersicht'}"
        )
        st.caption(
            "Prototyp für ein Lagecockpit zur Sicherheit und Steuerung von Mikromobilität."
        )
    with header_col_right:
        if logo_path:
            # Logo vergrößert
            st.image(logo_path, width=190)

    st.markdown("---")

    # =========================================================
    # BASISDATEN & FARBEN (in Anlehnung an AL-Prototyp)
    # =========================================================

    CITY_DATA = [
        {"zone": "Zürich Innenstadt", "lat": 47.3769, "lon": 8.5417},
        {"zone": "Zürich West", "lat": 47.3890, "lon": 8.5000},
        {"zone": "Bern Zentrum", "lat": 46.9480, "lon": 7.4474},
        {"zone": "Bern Wankdorf", "lat": 46.9650, "lon": 7.4640},
        {"zone": "Luzern Altstadt", "lat": 47.0502, "lon": 8.3093},
        {"zone": "Basel Bahnhof", "lat": 47.5475, "lon": 7.5890},
        {"zone": "Winterthur Bahnhof", "lat": 47.5000, "lon": 8.7240},
        {"zone": "St. Gallen Zentrum", "lat": 47.4245, "lon": 9.3767},
        {"zone": "Lausanne Gare", "lat": 46.5160, "lon": 6.6291},
        {"zone": "Genf Cornavin", "lat": 46.2100, "lon": 6.1423},
    ]

    ZONES = [c["zone"] for c in CITY_DATA]

    RISK_COLOR_MAP = {
        "niedrig": [46, 204, 113, 160],   # grünlich
        "mittel": [241, 196, 15, 180],    # gelb
        "hoch": [230, 126, 34, 200],      # orange
        "kritisch": [231, 76, 60, 220],   # rot
    }

    # =========================================================
    # FUNKTION FÜR LIVE-DATEN (angelehnt an AL)
    # =========================================================
    def generate_live_data(scenario: str):
        """
        Generiert Fake-Live-Daten für mehrere Städte:
        - Zonenrisiko & Blockierungszeit
        - Trenddaten (Rides, Reports, Tech-Issues)
        - Flottenstatus
        - Batterielevel
        - Meldungstabelle
        """
        rng = np.random.default_rng()

        base_bias = np.array([2.0] * len(ZONES))

        if "Pendler" in scenario:
            base_bias += np.array([1.5, 1.0, 0.8, 0.4, 0.4, 0.8, 0.5, 0.7, 0.2, 0.3])
        elif "Nightlife" in scenario:
            base_bias += np.array([1.2, 0.6, 0.8, 1.0, 1.0, 0.7, 0.4, 0.8, 0.3, 0.4])
        elif "Schulweg" in scenario:
            base_bias += np.array([0.4, 0.8, 0.3, 0.2, 0.2, 0.7, 0.4, 0.3, 0.2, 0.5])
        elif "Baustellen" in scenario:
            base_bias += rng.uniform(0.3, 1.5, size=len(ZONES))

        # Risiko-Scores 1–4
        risk_scores = np.clip(
            np.round(base_bias + rng.normal(0, 0.6, size=len(ZONES))),
            1,
            4,
        )

        # Incidents & Blockierungen
        incidents_5 = rng.integers(0, 10, size=len(ZONES))
        incidents_30 = incidents_5 + rng.integers(0, 20, size=len(ZONES))
        incidents_24 = incidents_30 + rng.integers(0, 60, size=len(ZONES))
        blocked_min = np.clip(risk_scores * 10 + rng.normal(0, 6, size=len(ZONES)), 0, None)

        # Trenddaten (letzte 2 Stunden, 5-Minuten-Takt)
        now = datetime.now()
        times = [now - timedelta(minutes=5 * i) for i in range(24)][::-1]

        if "Nightlife" in scenario:
            base_flow = np.linspace(40, 120, len(times))
        elif "Pendler" in scenario:
            base_flow = np.linspace(30, 150, len(times))
        elif "Schulweg" in scenario:
            base_flow = np.linspace(20, 80, len(times))
        else:
            base_flow = np.linspace(25, 100, len(times))

        crowd_flow = np.clip(base_flow + rng.normal(0, 15, len(times)), 5, None)
        citizen_reports = np.clip(crowd_flow / 12 + rng.normal(0, 1.5, len(times)), 0, None)
        tech_issues = np.clip(
            rng.normal(loc=crowd_flow / 60, scale=0.5, size=len(times)), 0, None
        )

        df_trend = pd.DataFrame(
            {
                "timestamp": times,
                "rides": crowd_flow,
                "reports": citizen_reports,
                "tech_issues": tech_issues,
            }
        )

        # Zonen-DataFrame
        risk_level_map = {1: "niedrig", 2: "mittel", 3: "hoch", 4: "kritisch"}

        df_zones = pd.DataFrame(CITY_DATA)
        df_zones["risk_score"] = risk_scores
        df_zones["risk_label"] = df_zones["risk_score"].map(risk_level_map)
        df_zones["incidents_5min"] = incidents_5
        df_zones["incidents_30min"] = incidents_30
        df_zones["incidents_24h"] = incidents_24
        df_zones["blocked_min"] = blocked_min

        # Map-DataFrame
        df_map = df_zones.copy()
        df_map["color"] = df_map["risk_label"].map(RISK_COLOR_MAP)

        # Flottenstatus
        fleet_rows = []
        status_keys = ["free", "reserved", "in_use", "blocked"]
        status_labels = {
            "free": "Frei verfügbar",
            "reserved": "Online reserviert",
            "in_use": "In Fahrt",
            "blocked": "Gesperrt / offline",
        }

        for _, row in df_zones.iterrows():
            total = rng.integers(80, 200)
            # Verteilung abhängig vom Risiko
            if row["risk_label"] in ["hoch", "kritisch"]:
                weights = np.array([0.45, 0.15, 0.30, 0.10])
            else:
                weights = np.array([0.60, 0.10, 0.25, 0.05])

            counts = (total * weights).round().astype(int)
            for key, count in zip(status_keys, counts):
                fleet_rows.append(
                    {
                        "zone": row["zone"],
                        "status_key": key,
                        "status": status_labels[key],
                        "count": int(count),
                    }
                )

        df_fleet = pd.DataFrame(fleet_rows)

        # Batterie-Levels
        battery_levels = np.clip(
            rng.normal(loc=65, scale=18, size=2000), 0, 100
        )
        df_battery = pd.DataFrame({"battery_level": battery_levels})

        # Meldungs-Feed
        templates = [
            "Nutzer-Meldung: Gefährliche Querung in {zone}",
            "E-Scooter blockiert Fussweg in {zone}",
            "Mehrere Scooter umgestossen in {zone}",
            "Hohe Geschwindigkeiten von Scootern in {zone}",
            "Polizeimeldung: Unfall mit Scooter in {zone}",
            "ÖV-Meldung: Haltestelle beeinträchtigt in {zone}",
            "Kontrolle: Scooter falsch parkiert in {zone}",
            "Baustelle: Umleitung betrifft Scooter-Route in {zone}",
            "Anwohnerbeschwerde zu Lärm in {zone}",
            "Technik: Connectivity-Probleme in {zone}",
        ]
        zones_for_msgs = rng.choice(ZONES, size=10)
        times_str = [
            (now - timedelta(minutes=int(m))).strftime("%H:%M")
            for m in rng.integers(1, 45, size=10)
        ]
        meldungen = [
            templates[i].format(zone=zones_for_msgs[i]) for i in range(10)
        ]
        df_reports = pd.DataFrame(
            {
                "zeit": times_str,
                "zone": zones_for_msgs,
                "meldung": meldungen,
                "prio": rng.choice(
                    ["hoch", "mittel", "niedrig"], size=10, p=[0.4, 0.4, 0.2]
                ),
            }
        )

        return df_zones, df_trend, df_map, df_reports, df_fleet, df_battery


    # =========================================================
    # SIDEBAR: PERSONA, SZENARIO, ANSICHT (AL-Style)
    # =========================================================
    st.sidebar.header("Steuerung")

    persona = st.sidebar.selectbox(
        "Persona",
        [
            "Leitstelle Stadtverkehr",
            "Polizei / Sicherheit",
            "Stadtverwaltung / Ordnungsamt",
            "ÖV-Planung",
        ],
        index=[
            "Leitstelle Stadtverkehr",
            "Polizei / Sicherheit",
            "Stadtverwaltung / Ordnungsamt",
            "ÖV-Planung",
        ].index(role)
        if role in ROLE_LABEL
        else 0,
    )

    scenario = st.sidebar.selectbox(
        "Szenario",
        [
            "Pendler:innen Spitzenzeit",
            "Wochenend-Nacht / Nightlife",
            "Schulweg-Sicherheit",
            "Baustellen & Umleitungen",
        ],
    )

    view_mode = st.sidebar.radio(
        "Ansicht",
        ["1 – Echtzeit-Heatmap", "2 – Trend / Analyse", "3 – Reporting"],
    )

    # =========================================================
    # LIVE-DATEN LADEN
    # =========================================================
    if scenario not in st.session_state.data_cache:
        st.session_state.data_cache[scenario] = generate_live_data(scenario)

    df_zones, df_trend, df_map, df_reports, df_fleet, df_battery = st.session_state.data_cache[
        scenario
]


    global_safety_index = int(
        np.clip(
            100 - df_zones["risk_score"].mean() * 18 - df_zones["blocked_min"].mean() / 4,
            0,
            100,
        )
    )
    num_critical = int((df_zones["risk_label"] == "kritisch").sum())
    num_high = int((df_zones["risk_label"] == "hoch").sum())
    avg_blocked = int(df_zones["blocked_min"].mean())
    total_scooters = int(df_fleet["count"].sum())
    share_low_battery = int(
        (df_battery["battery_level"] < 20).mean() * 100
    )

    # =========================================================
    # PUSH-NACHRICHT + VORGEFERTIGTE NACHRICHTEN + RELOAD-BUTTON IN SIDEBAR
    # =========================================================
    with st.sidebar:
        high_prio = df_reports[df_reports["prio"] == "hoch"].head(1)
        if not high_prio.empty:
            row = high_prio.iloc[0]
            zone_txt = row["zone"]
            msg_txt = row["meldung"].split(": ", 1)[-1]
        else:
            zone_txt = "Altstadt"
            msg_txt = "Demonstration gemeldet"

        # Push-Nachricht (wie vorher)
        st.markdown(
            f"""
            <div style="
                background-color:#FFF7E0;
                border:1px solid #F1C232;
                border-radius:8px;
                padding:10px 12px;
                font-size:0.85rem;
                line-height:1.3;
                margin-bottom:10px;
            ">
                <strong> 1 neue Meldung</strong><br>
                {zone_txt}: {msg_txt}<br>
                <span style="font-size:0.78rem;color:#555;">
                    Diese Optionen nutzt ihr im Test, um Szenarien zu variieren.
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Card-Rahmen für vorgefertigte Nachrichten
        st.markdown(
            """
            <div style="
                background-color:#F4F6FF;
                border:1px solid #D0D4FF;
                border-radius:8px;
                padding:10px 12px;
                margin-bottom:10px;
            ">
            """,
            unsafe_allow_html=True,
        )

        st.markdown("**📨 Vorgefertigte Nachrichten**")
        st.markdown(
            '<span style="font-size:0.78rem;color:#555;">'
            "Schnellmeldungen an Verwaltung & Partnerorganisationen (Prototyp)."
            "</span>",
            unsafe_allow_html=True,
        )

        # Auswahl der Nachricht (Mock)
        message_options = [
            "Stadtverwaltung: Bericht zu Hotspot aktualisieren",
            "Polizei: Zusätzliche Patrouille im Bereich anfragen",
            "ÖV-Betriebe: Haltestelle durch Scooter beeinträchtigt",
        ]
    
        selected_template = st.radio(
            "",
            message_options,
            index=0,
            label_visibility="collapsed",
            key="template_choice",
        )
        body=selected_template
        
        #Sendet Notification an den Brwoser(braucht push file)

        if st.button("📤 Nachricht absenden"):
            send_alert(body)
        

        st.markdown("</div>", unsafe_allow_html=True)

        if st.button("🔄 Live-Daten neu laden"):
            # Remove cached data for the currently selected scenario
            st.session_state.data_cache.pop(scenario, None)
            st.rerun()

#Test Feedback ab hier
        


        def open_feedback():
            st.session_state.show_feedback = True


        def close_feedback():
            st.session_state.show_feedback = False

        st.button("💬 Feedback Formular", on_click=open_feedback)
        
        if st.session_state.show_feedback:
            if hasattr(st, "modal"):
                modal_ctx = st.dialog("We'd love your feedback!")
            else:
                st.warning("Streamlit Pop up ist in diesem Brwoser nicht supported..")
                modal_ctx = st.container()

            with modal_ctx:
                st.write("Bitte bewerten Sie Ihre Erfahrungen mit diesem Dashboard.")

                # Use a form so everything submits together
                with st.form("feedback_form"):
                    col1, col2 = st.columns(2)

                    with col1:
                        happiness = st.slider(
                            "Wie zufrieden waren Sie mit der Nutzung dieses Dashboards?",
                            min_value=1,
                            max_value=5,
                            value=4,
                            help="1 = Überhaupt nicht zufrieden, 5 = Sehr zufrieden",
                        )

                        usability = st.slider(
                            "Wie würden Sie die Benutzerfreundlichkeit des Dashboards bewerten?",
                            min_value=1,
                            max_value=5,
                            value=4,
                            help="1 = Sehr schwer zu bedienen, 5 = Sehr einfach zu bedienen",
                        )

                    with col2:
                        methods = st.slider(
                            "Wie zufrieden waren Sie mit den vorgeschlagenen Methoden des Dashboards?",
                            min_value=1,
                            max_value=5,
                            value=4,
                            help="1 Überhaupt nicht zufrieden, 5 = Sehr zufrieden",
                        )

                    comments = st.text_area(
                        "Möchten Sie uns noch etwas mitteilen?",
                        placeholder="Geben Sie hier Ihr Feedback ein...",
                )

                    submitted = st.form_submit_button("Feedback absenden")

            if submitted:
                # Prepare feedback entry
                feedback_entry = {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "happiness_usage": happiness,
                    "usability": usability,
                    "happiness_methods": methods,
                    "comments": comments,
                }

                # --- Save to local Excel file ---
                file_path = "feedback.xlsx"

                if os.path.exists(file_path):
                    # Append to existing file
                    existing_df = pd.read_excel(file_path)
                    new_df = pd.concat(
                        [existing_df, pd.DataFrame([feedback_entry])],
                        ignore_index=True,
                    )
                else:
                    # Create new file
                    new_df = pd.DataFrame([feedback_entry])

                new_df.to_excel(file_path, index=False)

                st.success("✅ Vielen Dank! Ihr Feedback wurde gespeichert.")
                close_feedback()

    # =========================================================
    # ANSICHT 1 – HEATMAP & HOTSPOTS
    # =========================================================
    if view_mode.startswith("1"):
        st.subheader("1️⃣ Echtzeit-Heatmap & Hotspots")

        center_lat = df_map["lat"].mean()
        center_lon = df_map["lon"].mean()

        view_state = pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=7.2,
            pitch=45,
        )

        layer_scatter = pdk.Layer(
            "ScatterplotLayer",
            data=df_map,
            get_position="[lon, lat]",
            get_radius="risk_score * 9000",
            get_fill_color="color",
            pickable=True,
            opacity=0.8,
        )

        layer_heat = pdk.Layer(
            "HeatmapLayer",
            data=df_map,
            get_position="[lon, lat]",
            get_weight="risk_score",
            radius_pixels=70,
        )

        st.pydeck_chart(
            pdk.Deck(
                map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
                initial_view_state=view_state,
                layers=[layer_heat, layer_scatter],
                tooltip={
                    "html": (
                        "<b>Zone:</b> {zone}<br/>"
                        "<b>Risiko:</b> {risk_label}<br/>"
                        "<b>Incidents 30min:</b> {incidents_30min}"
                    ),
                    "style": {"font-size": "12px"},
                },
            ),
            use_container_width=True,
        )

        st.markdown("### Top-Hotspots (letzte 30 Minuten)")

        df_hot = df_zones.sort_values(
            ["risk_score", "incidents_30min", "blocked_min"],
            ascending=[False, False, False],
        ).head(6)

        df_hot_view = df_hot[
            [
                "zone",
                "risk_label",
                "incidents_30min",
                "blocked_min",
                "incidents_24h",
            ]
        ].rename(
            columns={
                "zone": "Zone",
                "risk_label": "Risiko",
                "incidents_30min": "Incidents 30min",
                "blocked_min": "Blockiert (min)",
                "incidents_24h": "Incidents 24h",
            }
        )
        st.dataframe(df_hot_view, use_container_width=True, hide_index=True)

    # =========================================================
    # ANSICHT 2 – TREND / ANALYSE
    # =========================================================
    elif view_mode.startswith("2"):
        st.subheader("2️⃣ Trend & Analyse – Auslastung und Meldungen")

        c1, c2 = st.columns([2, 1.2])

        with c1:
            st.markdown("#### Fahrten & Meldungen (letzte 2 Stunden)")
            df_long = df_trend.melt(
                id_vars="timestamp",
                value_vars=["rides", "reports", "tech_issues"],
                var_name="Kennzahl",
                value_name="Wert",
            )
            kennzahl_labels = {
                "rides": "Fahrten",
                "reports": "Meldungen (Nutzer:innen)",
                "tech_issues": "Technische Issues",
            }
            df_long["Kennzahl"] = df_long["Kennzahl"].map(kennzahl_labels)

            chart = (
                alt.Chart(df_long)
                .mark_line(point=True)
                .encode(
                    x=alt.X("timestamp:T", title="Zeit"),
                    y=alt.Y("Wert:Q"),
                    color=alt.Color("Kennzahl:N"),
                    tooltip=["timestamp:T", "Kennzahl:N", "Wert:Q"],
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)

        with c2:
            st.markdown("#### Risikoprofil nach Stadt")
            df_risk_bar = df_zones[["zone", "risk_score"]].copy()
            df_risk_bar["Risiko-Score"] = df_risk_bar["risk_score"]
            bar_chart = (
                alt.Chart(df_risk_bar)
                .mark_bar()
                .encode(
                    x=alt.X("Risiko-Score:Q"),
                    y=alt.Y("zone:N", sort="-x", title="Zone"),
                    tooltip=["zone:N", "Risiko-Score:Q"],
                )
                .properties(height=300)
            )
            st.altair_chart(bar_chart, use_container_width=True)

        st.markdown("### Meldungen-Feed (Auswahl)")
        st.dataframe(
            df_reports.sort_values("prio", ascending=True),
            use_container_width=True,
            hide_index=True,
        )

    # =========================================================
    # ANSICHT 3 – REPORTING & FLOTTE
    # =========================================================
    else:
        st.subheader("3️⃣ Reporting & Flottenstatus")

        c1, c2 = st.columns([1.5, 1.5])

        with c1:
            st.markdown("#### Flottenstatus nach Stadt")
            df_fleet_pivot = (
                df_fleet.pivot_table(
                    index="zone",
                    columns="status",
                    values="count",
                    aggfunc="sum",
                )
                .fillna(0)
                .reset_index()
            )
            st.dataframe(df_fleet_pivot, use_container_width=True, hide_index=True)

        with c2:
            st.markdown("#### Batterie-Level der Flotte")
            hist_chart = (
                alt.Chart(df_battery)
                .mark_bar()
                .encode(
                    x=alt.X("battery_level:Q", bin=alt.Bin(maxbins=20), title="Batterielevel (%)"),
                    y=alt.Y("count():Q", title="Anzahl Scooter"),
                    tooltip=["count():Q"],
                )
                .properties(height=280)
            )
            st.altair_chart(hist_chart, use_container_width=True)

            st.metric("Scooter mit < 20% Batterie", f"{share_low_battery}%")

        st.markdown("### Zusammenfassung für Entscheidungsträger:innen")
        st.markdown(
            f"""
            - **Globaler Safety-Index:** {global_safety_index}/100  
            - **Kritische Städte:** {num_critical} (rote Stufe)  
            - **Hohe Risiken:** {num_high} (orange Stufe)  
            - **Ø Blockierung:** {avg_blocked} Minuten pro Zone     

            Nutze diese Sicht für tägliche Lagebesprechungen, Priorisierung von Einsätzen
            und Abstimmung zwischen **{role_label}** und weiteren Akteuren.
            """
        )
