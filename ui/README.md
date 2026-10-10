# Product manager workbench

`app.py` is the primary Streamlit interface: requirement queue, evidence and exact excerpts, score contributions, uncertainty, review actions and audit history. `hosting_access.py` adds the prototype's hosted access gate and private database setup.

Run from the repository root with `uv run streamlit run ui/app.py`. Domain logic belongs in `src/bmw_pm/`; the UI calls services. The optional YouTube browser is a collector interface, not a second requirement approval system.
