# Gatherly AI ✦

Gatherly AI is an AI-powered event planning application that uses Qloo cultural intelligence to help users discover places and plan events.

## Features
- Create personalized event plans
- Search places using the Qloo API
- Explore recommendations based on event type and interests
- Calculate budget per guest
- Track research activity
- Save and manage events
- Export saved events as JSON
- Dark-themed Streamlit dashboard

## Technology Stack
- Python
- Streamlit
- Qloo API

## Run Locally
1. Clone this repository.
2. Create and activate a Python virtual environment.
3. Install the required Python packages.
4. Configure your Qloo API key in Streamlit secrets.
5. Run the application:

   `python -m streamlit run app.py`

## API Configuration
Create `.streamlit/secrets.toml` and add your Qloo API key:

```toml
QLOO_API_KEY = "your_api_key_here"