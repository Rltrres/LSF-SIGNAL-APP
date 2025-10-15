
# LSF Signal Tool (Streamlit)

A simple web app that turns your current chart state into a trade signal using your LSF core rules:
- CISD + POI validation
- VWAP side/slope
- ADX expansion
- Deviation targets (2.5σ, 4σ) from CISD anchor

## Run locally
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy (free options)
- **Streamlit Community Cloud**: Push these files to a public GitHub repo and point Streamlit at `app.py`.
- **Render / Railway**: Use the same command; set a web service with the start command above.

## Notes
- Tick size / 1σ in ticks are configurable in the sidebar.
- If Risk(ticks) is blank, the app uses the default from the sidebar.
- Entry is current price for MARKET or your specified limit for LIMIT.
