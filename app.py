import gradio as gr
import requests
import json
import os
from openai import OpenAI
from datetime import datetime

# Load from env if available (set as HF Secrets)
ENV_OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ENV_OWM_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

CRISIS_THRESHOLDS = {
    "Drought": "Soil moisture < 20% AND humidity < 30%",
    "Frost": "Temperature < 2°C OR soil temp < 1°C",
    "Heat Stress": "Temperature > 38°C",
    "Flooding Risk": "Soil moisture > 85%",
    "Storm Risk": "Wind speed > 15 m/s",
}

SEVERITY_COLORS = {
    "low": ("🟢", "#dcfce7", "#166534"),
    "medium": ("🟡", "#fef9c3", "#854d0e"),
    "high": ("🟠", "#ffedd5", "#9a3412"),
    "critical": ("🔴", "#fee2e2", "#991b1b"),
}

EXAMPLE_SCENARIOS = [
    ["Fresno, CA", 15, 25, 6.5, "Drought scenario: low soil moisture"],
    ["Phoenix, AZ", 12, 44, 7.0, "Heat stress + drought combo"],
    ["Minneapolis, MN", 55, 0.5, 6.8, "Frost risk: soil temp near zero"],
    ["Seattle, WA", 90, 14, 5.5, "Flooding risk: saturated soil"],
    ["Dallas, TX", 45, 22, 6.7, "Normal — all clear"],
]


def fetch_weather(city: str, api_key: str):
    if not api_key:
        return None, "No OpenWeatherMap API key — weather data unavailable"
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={api_key}&units=metric"
    )
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        d = r.json()
        return {
            "temperature_c": round(d["main"]["temp"], 1),
            "humidity_pct": d["main"]["humidity"],
            "weather_condition": d["weather"][0]["main"],
            "wind_speed_ms": round(d["wind"]["speed"], 1),
            "location": d["name"],
            "feels_like": round(d["main"]["feels_like"], 1),
        }, None
    except requests.exceptions.HTTPError as e:
        return None, f"Weather API error: {e.response.status_code} — check city name or API key"
    except Exception as e:
        return None, f"Weather fetch failed: {str(e)}"


def build_analysis_prompt(weather: dict, soil_moisture: float, soil_temp: float, soil_ph: float) -> str:
    return f"""Analyze these farm sensor readings and determine if there is a crisis requiring immediate action.

Location: {weather['location']}
Temperature: {weather['temperature_c']}°C (feels like {weather['feels_like']}°C)
Humidity: {weather['humidity_pct']}%
Weather Condition: {weather['weather_condition']}
Wind Speed: {weather['wind_speed_ms']} m/s
Soil Moisture: {soil_moisture}%
Soil Temperature: {soil_temp}°C
Soil pH: {soil_ph}
Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

Crisis thresholds:
- Drought: soil moisture below 20% AND humidity below 30%
- Frost: temperature below 2°C OR soil temperature below 1°C
- Heat stress: temperature above 38°C
- Flooding risk: soil moisture above 85%
- Storm risk: wind speed above 15 m/s

Return ONLY a JSON object with these exact keys:
{{
  "is_crisis": false,
  "crisis_type": "none",
  "severity": "low",
  "recommended_action": "Monitor conditions. All readings within normal range.",
  "farmer_message": "All sensors normal. No action needed.",
  "buyer_message": "Operations normal. No supply disruptions expected.",
  "key_concern": "Briefly describe the most notable reading even if not a crisis"
}}

Severity must be one of: low, medium, high, critical."""


def analyze_farm(city, soil_moisture, soil_temp, soil_ph, openai_key_input, owm_key_input):
    oai_key = openai_key_input.strip() or ENV_OPENAI_KEY
    owm_key = owm_key_input.strip() or ENV_OWM_KEY

    if not oai_key:
        return (
            "❌ OpenAI API key required. Enter it above or set OPENAI_API_KEY as a Space secret.",
            "", "", "", "", "", ""
        )

    # Fetch live weather
    weather, weather_err = fetch_weather(city.strip(), owm_key)
    weather_note = ""
    if weather_err or not weather:
        weather_note = f"⚠️ {weather_err} — using estimated values."
        weather = {
            "temperature_c": 25.0,
            "humidity_pct": 60.0,
            "weather_condition": "Unknown",
            "wind_speed_ms": 5.0,
            "location": city.strip(),
            "feels_like": 25.0,
        }
        weather_display = f"⚠️ Live weather unavailable | Location: {city}"
    else:
        weather_display = (
            f"📍 {weather['location']}  |  "
            f"🌡️ {weather['temperature_c']}°C  |  "
            f"💧 {weather['humidity_pct']}% humidity  |  "
            f"🌬️ {weather['wind_speed_ms']} m/s wind  |  "
            f"☁️ {weather['weather_condition']}"
        )

    # Call OpenAI
    try:
        client = OpenAI(api_key=oai_key)
        prompt = build_analysis_prompt(weather, soil_moisture, soil_temp, soil_ph)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an agricultural crisis detection AI. "
                        "Analyze farm sensor data precisely. "
                        "Return only valid JSON matching the requested schema exactly."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
    except Exception as e:
        return f"❌ OpenAI error: {str(e)}", "", "", "", "", "", ""

    is_crisis = result.get("is_crisis", False)
    crisis_type = result.get("crisis_type", "none")
    severity = result.get("severity", "low").lower()
    action = result.get("recommended_action", "")
    farmer_msg = result.get("farmer_message", "")
    buyer_msg = result.get("buyer_message", "")
    key_concern = result.get("key_concern", "")

    emoji, _, _ = SEVERITY_COLORS.get(severity, ("🟢", "#dcfce7", "#166534"))

    if is_crisis:
        status = f"🚨 CRISIS DETECTED  ·  {crisis_type.upper()}  ·  Severity: {severity.upper()}  {emoji}"
    else:
        status = f"✅ ALL CLEAR — No crisis detected  ·  Key concern: {key_concern}"

    if weather_note:
        weather_display += f"\n{weather_note}"

    severity_display = f"{emoji} {severity.upper()}" if is_crisis else "🟢 LOW — No action needed"

    return status, weather_display, severity_display, action, farmer_msg, buyer_msg, key_concern


def load_example(city, moisture, temp, ph, _label):
    return city, moisture, temp, ph


# ── UI ──────────────────────────────────────────────────────────────────────
CSS = """
.header-box { text-align: center; padding: 1.5rem 0 0.5rem; }
.status-crisis { background: #fef2f2 !important; border: 2px solid #ef4444 !important; border-radius: 8px; font-weight: bold; }
.status-clear  { background: #f0fdf4 !important; border: 2px solid #22c55e !important; border-radius: 8px; font-weight: bold; }
.threshold-table th { background: #f0fdf4; }
footer { display: none !important; }
"""

with gr.Blocks(
    title="🌾 Smart Farm Crisis Response Agent",
    theme=gr.themes.Soft(primary_hue="green", secondary_hue="teal"),
    css=CSS,
) as demo:

    gr.HTML("""
    <div class="header-box">
      <h1 style="font-size:2rem; margin-bottom:0.25rem;">🌾 Smart Farm Crisis Response Agent</h1>
      <p style="color:#6b7280; font-size:1rem; margin:0;">
        Real-time AI detection of drought · frost · heat stress · flooding · storms
      </p>
      <p style="color:#9ca3af; font-size:0.85rem; margin-top:0.5rem;">
        Powered by OpenWeatherMap + GPT-4o-mini · mirrors the live n8n workflow
      </p>
    </div>
    """)

    with gr.Tabs():

        # ── Tab 1: Analyze ─────────────────────────────────────────────────
        with gr.Tab("🔍 Analyze"):
            with gr.Row():

                # Left column — inputs
                with gr.Column(scale=1, min_width=300):

                    with gr.Group():
                        gr.Markdown("#### 🔑 API Keys")
                        openai_key_in = gr.Textbox(
                            label="OpenAI API Key",
                            placeholder="sk-... (or set OPENAI_API_KEY env var)",
                            type="password",
                        )
                        owm_key_in = gr.Textbox(
                            label="OpenWeatherMap API Key",
                            placeholder="(or set OPENWEATHER_API_KEY env var)",
                            type="password",
                        )

                    with gr.Group():
                        gr.Markdown("#### 📍 Farm Location")
                        city_in = gr.Textbox(
                            label="City / Region",
                            value="Fresno, CA",
                            placeholder="e.g. Fresno, CA  or  Mumbai  or  Berlin",
                        )

                    with gr.Group():
                        gr.Markdown("#### 🪱 Soil Sensor Readings")
                        moisture_in = gr.Slider(
                            label="Soil Moisture (%)",
                            minimum=0, maximum=100, value=45, step=1,
                        )
                        soiltemp_in = gr.Slider(
                            label="Soil Temperature (°C)",
                            minimum=-10, maximum=60, value=20, step=0.5,
                        )
                        ph_in = gr.Slider(
                            label="Soil pH",
                            minimum=3.0, maximum=10.0, value=6.5, step=0.1,
                        )

                    analyze_btn = gr.Button(
                        "🔍  Analyze Farm Conditions", variant="primary", size="lg"
                    )

                # Right column — outputs
                with gr.Column(scale=1, min_width=300):
                    gr.Markdown("#### 📊 Analysis Results")

                    status_out = gr.Textbox(
                        label="Crisis Status", interactive=False, lines=2
                    )
                    weather_out = gr.Textbox(
                        label="Live Weather", interactive=False, lines=2
                    )

                    with gr.Row():
                        severity_out = gr.Textbox(
                            label="Severity", interactive=False, scale=1
                        )
                        concern_out = gr.Textbox(
                            label="Key Concern", interactive=False, scale=2
                        )

                    action_out = gr.Textbox(
                        label="⚡ Recommended Action", interactive=False, lines=2
                    )

                    gr.Markdown("#### 📱 Auto-Generated Alerts")
                    farmer_out = gr.Textbox(
                        label="WhatsApp → Farmer", interactive=False, lines=3
                    )
                    buyer_out = gr.Textbox(
                        label="Email → Crop Buyers", interactive=False, lines=4
                    )

            analyze_btn.click(
                fn=analyze_farm,
                inputs=[city_in, moisture_in, soiltemp_in, ph_in, openai_key_in, owm_key_in],
                outputs=[status_out, weather_out, severity_out, action_out, farmer_out, buyer_out, concern_out],
            )

        # ── Tab 2: Quick Scenarios ──────────────────────────────────────────
        with gr.Tab("⚡ Quick Scenarios"):
            gr.Markdown("""
### Pre-loaded test scenarios
Click a row to load it into the Analyze tab, then switch over and hit **Analyze**.
            """)

            scenario_city = gr.Textbox(visible=False)
            scenario_moisture = gr.Slider(visible=False, minimum=0, maximum=100)
            scenario_temp = gr.Slider(visible=False, minimum=-10, maximum=60)
            scenario_ph = gr.Slider(visible=False, minimum=3.0, maximum=10.0)

            for row in EXAMPLE_SCENARIOS:
                with gr.Row():
                    gr.Markdown(f"**{row[4]}**")
                    btn = gr.Button(f"Load: {row[0]} · moisture={row[1]}% · temp={row[2]}°C", size="sm")
                    btn.click(
                        fn=lambda c=row[0], m=row[1], t=row[2], p=row[3]: (c, m, t, p),
                        outputs=[city_in, moisture_in, soiltemp_in, ph_in],
                    )

        # ── Tab 3: How It Works ─────────────────────────────────────────────
        with gr.Tab("📖 How It Works"):
            gr.Markdown("""
## Architecture

This UI mirrors the live **n8n Smart Farm Crisis Response Agent** workflow:

```
Schedule Trigger (every 15 min)
  → Fetch Weather (OpenWeatherMap)
  → Normalize Weather Data
  → Fetch Soil Sensor Data (IoT / Ubidots)
  → Combine Sensor Data
  → AI Agent (GPT-4o-mini) — analyzes all readings
  → Extract AI Analysis
  → Crisis Detected?
      ├── YES → WhatsApp Alert (Twilio) → Email Buyers (Gmail) → Trigger Irrigation
      └── NO  → Log All Clear
```

## Crisis Thresholds

| Crisis | Condition |
|--------|-----------|
| 🏜️ Drought | Soil moisture < 20% **AND** humidity < 30% |
| 🥶 Frost | Temperature < 2°C **OR** soil temp < 1°C |
| 🔥 Heat Stress | Temperature > 38°C |
| 🌊 Flooding Risk | Soil moisture > 85% |
| 🌪️ Storm Risk | Wind speed > 15 m/s |

## Severity Levels

| Level | Meaning |
|-------|---------|
| 🟢 Low | Within normal range |
| 🟡 Medium | Watch closely |
| 🟠 High | Immediate attention needed |
| 🔴 Critical | Emergency — act now |

## Setting Up for Production

1. Fork this Space and add `OPENAI_API_KEY` + `OPENWEATHER_API_KEY` as **Secrets**
2. Connect your real IoT sensor API in the n8n workflow
3. Add your Twilio + Gmail credentials in n8n
4. Activate the workflow — it runs every 15 minutes automatically

## Links

- 🔗 [n8n Workflow](https://aravind5.app.n8n.cloud/workflow/3YhdfeaAg8uz8eEc)
- 🌦️ [Get OpenWeatherMap API Key](https://openweathermap.org/api)
- 🤖 [Get OpenAI API Key](https://platform.openai.com/api-keys)
            """)

    gr.HTML("""
    <div style="text-align:center; color:#9ca3af; font-size:0.8rem; padding: 1rem 0 0.5rem;">
      Smart Farm Crisis Response Agent · Built with Gradio + OpenAI + OpenWeatherMap
    </div>
    """)

if __name__ == "__main__":
    demo.launch(show_error=True)
