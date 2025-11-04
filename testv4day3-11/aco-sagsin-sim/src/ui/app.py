import json
from pathlib import Path

import requests
import streamlit as st

st.set_page_config(page_title="ACO SAGSIN")

controller = st.text_input("Controller URL", value="http://localhost:8080")

col1, col2 = st.columns(2)
with col1:
    if st.button("Reload Config"):
        requests.post(f"{controller}/config/reload")
with col2:
    if st.button("Epoch"):
        requests.post(f"{controller}/simulate/set-epoch")

nodes = requests.get(f"{controller}/nodes").json()
links = requests.get(f"{controller}/links").json()

st.write(f"Nodes: {len(nodes)}, Links: {len(links)}")

if nodes:
    src = st.number_input("src id", min_value=0, max_value=max(n['id'] for n in nodes), value=0)
    dst = st.number_input("dst id", min_value=0, max_value=max(n['id'] for n in nodes), value=1)
    if st.button("Run ACO"):
        r = requests.post(f"{controller}/route", json={"src": int(src), "dst": int(dst)})
        st.json(r.json())
