"""Éléments partagés par les écrans : connexion à la base, cache, style, graphiques."""
import re

import pandas as pd
import streamlit as st

from core.db import DB

PALETTE = ["#4A2C1D", "#C9976B", "#8A5A3B", "#E3C4A3", "#5E7D4A", "#B5651D", "#7A6A5C"]
PLOTLY_CONFIG = {"displaylogo": False,
                 "toImageButtonOptions": {"format": "png", "filename": "ciat_insight", "scale": 2}}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


@st.cache_resource(show_spinner="Préparation de la base de données...")
def get_db():
    db = DB()
    db.init()
    return db


@st.cache_data(ttl=120, show_spinner=False)
def load(_db):
    return _db.load_all()


def refresh():
    """À appeler après chaque écriture pour que tous les écrans voient les nouvelles données."""
    load.clear()


def style():
    st.markdown("""
    <style>
      div[data-testid="stMetric"] {background: #F5EDE4; border-left: 4px solid #C9976B;
          padding: 10px 14px; border-radius: 6px;}
      div[data-testid="stMetricLabel"] p {font-size: 0.85rem;}
      h1, h2, h3 {color: #4A2C1D;}
      .ciat-note {font-size: 0.82rem; color: #7A6A5C;}
    </style>""", unsafe_allow_html=True)


def header(title, subtitle=None):
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def fmt_date(s):
    return pd.to_datetime(s, errors="coerce").dt.strftime("%d/%m/%Y").fillna("")


def plot(fig):
    fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), colorway=PALETTE,
                      font=dict(family="Arial"), legend_title_text="")
    st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)


def iso(d):
    return d.isoformat() if d else None
