"""A local, in-memory sandbox for one synthetic feedback statement."""
from __future__ import annotations

import json

import streamlit as st
from pydantic import ValidationError

from bmw_pm.mocktest import MockTestInput, run_mocktest


SAMPLES = {
    "Controls complaint": ("G60", "US", "ICE", "The climate control menu is hard to use while driving."),
    "Charging complaint": ("G70", "US", "BEV", "Charging is slow on cold journeys."),
    "Praise only": ("G70", "US", "ICE", "The seats are comfortable and the cabin is quiet."),
    "No keyword match": ("F70", "GB", "ICE", "I collected my car on Tuesday."),
    "Write my own": ("G60", "US", "ICE", ""),
}

st.set_page_config(page_title="BMW Agent Mock Test", layout="centered")
st.title("Agent mock test")
st.caption("Try one synthetic feedback statement against the project's deterministic keyword baseline.")
st.info("Local sandbox: no database write, external API call, LLM run, or financial score.")

sample_name = st.selectbox("Example", list(SAMPLES))
sample_model, sample_country, sample_powertrain, sample_text = SAMPLES[sample_name]
with st.form("mocktest_input"):
    left, middle, right = st.columns(3)
    with left:
        model_code = st.selectbox(
            "Vehicle", ["F70", "G60", "G70"],
            index=["F70", "G60", "G70"].index(sample_model), key=f"model_{sample_name}",
        )
    with middle:
        country = st.text_input("Market (ISO code)", value=sample_country, key=f"country_{sample_name}")
    with right:
        powertrain = st.selectbox(
            "Powertrain", ["ICE", "PHEV", "BEV"],
            index=["ICE", "PHEV", "BEV"].index(sample_powertrain), key=f"powertrain_{sample_name}",
        )
    feedback_text = st.text_area(
        "Customer feedback", value=sample_text, height=130,
        max_chars=2000, key=f"feedback_{sample_name}",
    )
    submitted = st.form_submit_button("Run mock test", type="primary")

if submitted:
    try:
        request = MockTestInput(
            model_code=model_code, country=country.strip().upper(),
            powertrain=powertrain, feedback_text=feedback_text,
        )
        result = run_mocktest(request)
    except (ValidationError, ValueError) as exc:
        st.error(f"Check the input: {exc}")
    else:
        st.divider()
        st.subheader("Result")
        st.caption(
            f"{request.model_code} · {request.country} · {request.powertrain} · "
            f"{result.provider_label} · taxonomy {result.taxonomy_version}"
        )
        if result.status == "candidate_for_review":
            st.success(f"{len(result.candidates)} provisional update candidate(s) for PM review")
        elif result.status == "no_update_proposed":
            st.info("A topic was found, but this statement does not support a new update. Praise and neutral observations do not create candidates.")
        else:
            st.warning("No configured topic matched. The baseline abstained; this is not evidence that no customer need exists.")

        if result.signals:
            st.subheader("Extracted signals")
            for signal in result.signals:
                with st.container(border=True):
                    st.write(f"**{signal.need_domain.replace('_', ' ').title()}** · {signal.polarity.value}")
                    st.write(f"Customer outcome: {signal.customer_outcome}")
                    for span in signal.evidence_spans:
                        st.write("Exact text used as evidence:")
                        st.code(span.text, language=None)
                        st.caption(f"Characters {span.start}–{span.end} in this mock input")

        if result.candidates:
            st.subheader("Provisional updates")
            for candidate in result.candidates:
                with st.container(border=True):
                    st.write(f"**{candidate.title}**")
                    st.write(candidate.customer_outcome)
                    st.caption("Requires PM and engineering review. Cost, revenue, feasibility, customer prevalence, and ranking are unknown.")

        st.caption("One synthetic statement is unscored. Exact spans are checked mechanically; meaning and priority still need review.")
        with st.expander("Structured output"):
            st.json(result.model_dump(mode="json"))
        st.download_button(
            "Download JSON", json.dumps(result.model_dump(mode="json"), indent=2),
            file_name="bmw_mocktest_result.json", mime="application/json",
        )
