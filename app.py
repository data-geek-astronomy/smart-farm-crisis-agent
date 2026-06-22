import gradio as gr
import requests
import json
import os
from openai import OpenAI
from datetime import datetime

ENV_OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
ENV_OWM_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

# bg (rgba), text color, border color, emoji
SEVERITY_STYLES = {
    "low":      ("rgba(34,197,94,0.15)",   "#86efac", "#22c55e", "🟢"),
    "medium":   ("rgba(234,179,8,0.15)",   "#fde047", "#eab308", "🟡"),
    "high":     ("rgba(249,115,22,0.15)",  "#fdba74", "#f97316", "🟠"),
    "critical": ("rgba(239,68,68,0.18)",   "#fca5a5", "#ef4444", "🔴"),
}

# ── Pre-computed demo scenarios (no API key required) ───────────────────────
DEMO_SCENARIOS = [
    {
        "city": "Fresno, CA",
        "label": "🏜️ Drought Emergency",
        "weather": {"temperature_c": 36.2, "humidity_pct": 18, "weather_condition": "Clear", "wind_speed_ms": 3.2},
        "soil":   {"moisture": 12, "temp": 28.5, "ph": 6.5},
        "result": {
            "is_crisis": True,
            "crisis_type": "Drought",
            "severity": "critical",
            "recommended_action": "Activate emergency irrigation immediately. Soil moisture critically low at 12%. Run all zones for 45+ minutes.",
            "farmer_message": "🚨 DROUGHT ALERT – Fresno: Soil moisture 12% (CRITICAL). Humidity 18%. START IRRIGATION NOW to prevent crop loss!",
            "buyer_message": (
                "Dear Buyer,\n\nUrgent supply chain notice: Extreme drought in Fresno, CA.\n"
                "Soil moisture: 12% | Humidity: 18% — Emergency irrigation activated.\n\n"
                "Potential 20-25% yield impact if conditions persist beyond 48 h.\n"
                "We will update you within 24 hours.\n\nSmart Farm Monitoring System"
            ),
            "key_concern": "Soil moisture 12% is well below the 20% drought threshold with humidity at 18%",
        },
    },
    {
        "city": "Phoenix, AZ",
        "label": "🔥 Heat Stress + Drought",
        "weather": {"temperature_c": 44.1, "humidity_pct": 12, "weather_condition": "Clear", "wind_speed_ms": 4.5},
        "soil":   {"moisture": 12, "temp": 40.2, "ph": 7.0},
        "result": {
            "is_crisis": True,
            "crisis_type": "Heat Stress",
            "severity": "high",
            "recommended_action": "Apply shade nets immediately. Increase irrigation to every 4 hours. Harvest heat-sensitive crops early.",
            "farmer_message": "⚠️ HEAT ALERT – Phoenix: Temp 44°C, soil 40°C. Apply shade nets NOW and increase watering!",
            "buyer_message": (
                "Dear Buyer,\n\nHeat stress warning — Phoenix, AZ: 44°C air, 40°C soil.\n"
                "Heat-sensitive crops may experience stress-related delays.\n\n"
                "Severity: High. Shade nets + increased irrigation deployed.\n"
                "Expect possible 10-15% volume reduction on heat-sensitive produce.\n\nSmart Farm Monitoring System"
            ),
            "key_concern": "Air temp 44.1°C exceeds the 38°C heat stress threshold by 6°C; soil also critically hot",
        },
    },
    {
        "city": "Minneapolis, MN",
        "label": "🥶 Frost Risk",
        "weather": {"temperature_c": 0.8, "humidity_pct": 78, "weather_condition": "Clouds", "wind_speed_ms": 6.1},
        "soil":   {"moisture": 55, "temp": 0.5, "ph": 6.8},
        "result": {
            "is_crisis": True,
            "crisis_type": "Frost",
            "severity": "high",
            "recommended_action": "Cover frost-sensitive crops immediately. Activate frost protection heating. Delay harvesting until temps rise above 4°C.",
            "farmer_message": "🥶 FROST ALERT – Minneapolis: Soil temp 0.5°C (below 1°C threshold). Cover all sensitive crops NOW!",
            "buyer_message": (
                "Dear Buyer,\n\nFrost risk advisory — Minneapolis, MN.\n"
                "Soil temperature: 0.5°C | Air: 0.8°C — Frost protection activated.\n\n"
                "Possible impact on leafy greens and root vegetables.\n"
                "We will confirm delivery timelines by tomorrow morning.\n\nSmart Farm Monitoring System"
            ),
            "key_concern": "Soil temp 0.5°C is below the 1°C frost threshold — immediate crop cover required",
        },
    },
    {
        "city": "Seattle, WA",
        "label": "🌊 Flooding Risk",
        "weather": {"temperature_c": 14.3, "humidity_pct": 92, "weather_condition": "Rain", "wind_speed_ms": 8.2},
        "soil":   {"moisture": 90, "temp": 12.1, "ph": 5.5},
        "result": {
            "is_crisis": True,
            "crisis_type": "Flooding Risk",
            "severity": "medium",
            "recommended_action": "Open drainage channels immediately. Stop all irrigation. Monitor soil hourly. Harvest mature crops early to prevent waterlogging.",
            "farmer_message": "⚠️ FLOOD RISK – Seattle: Soil moisture 90% (saturated). Open drains NOW and stop all irrigation!",
            "buyer_message": (
                "Dear Buyer,\n\nFlooding risk advisory — Seattle, WA.\n"
                "Soil moisture: 90% (saturated) | Heavy rainfall ongoing.\n\n"
                "Drainage systems activated. Possible delays on this week's orders.\n"
                "Status update within 12 hours.\n\nSmart Farm Monitoring System"
            ),
            "key_concern": "Soil moisture 90% exceeds 85% flooding threshold — root suffocation risk",
        },
    },
    {
        "city": "Dallas, TX",
        "label": "✅ All Clear",
        "weather": {"temperature_c": 24.8, "humidity_pct": 52, "weather_condition": "Partly Cloudy", "wind_speed_ms": 4.1},
        "soil":   {"moisture": 45, "temp": 22.0, "ph": 6.7},
        "result": {
            "is_crisis": False,
            "crisis_type": "none",
            "severity": "low",
            "recommended_action": "Continue standard monitoring. All conditions optimal. Next check in 15 minutes.",
            "farmer_message": "✅ ALL CLEAR – Dallas: Temp 24.8°C, moisture 45%, humidity 52%. All sensors normal.",
            "buyer_message": (
                "Dear Buyer,\n\nRoutine status — Dallas, TX operations.\n"
                "All farm conditions optimal: Temp 24.8°C | Moisture 45% | Humidity 52%.\n\n"
                "No disruptions anticipated. All orders on schedule.\n\nSmart Farm Monitoring System"
            ),
            "key_concern": "All conditions optimal — moisture 45%, temp 24.8°C, humidity 52%",
        },
    },
]


# ── HTML card builders ───────────────────────────────────────────────────────
def render_result(result: dict, weather: dict, city: str, weather_note: str = "") -> str:
    sev = result.get("severity", "low").lower()
    bg, txt, border, emoji = SEVERITY_STYLES.get(sev, SEVERITY_STYLES["low"])
    is_crisis = result.get("is_crisis", False)
    crisis_label = result.get("crisis_type", "none").upper() if is_crisis else "ALL CLEAR"
    header_icon = "🚨 CRISIS DETECTED —" if is_crisis else "✅"

    note_html = (
        f"<div style='background:rgba(234,179,8,0.15);border:1px solid rgba(234,179,8,0.4);"
        f"border-radius:6px;padding:8px 12px;font-size:0.82rem;margin-bottom:10px;color:#fde047;'>"
        f"⚠️ {weather_note}</div>"
        if weather_note else ""
    )

    return f"""
{note_html}
<div style="background:{bg};border:2px solid {border};border-radius:12px;padding:16px 20px;margin-bottom:12px;">
  <div style="font-size:1.25rem;font-weight:700;color:{txt};">
    {header_icon} {crisis_label} &nbsp; {emoji}
  </div>
  <div style="font-size:0.88rem;color:{txt};margin-top:4px;opacity:0.9;">
    Severity: <strong>{sev.upper()}</strong> &nbsp;|&nbsp; Location: <strong>{city}</strong>
  </div>
</div>

<div style="background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);border-radius:8px;padding:12px;margin-bottom:10px;font-size:0.88rem;color:#e2e8f0;">
  <span style="font-weight:600;color:#94a3b8;">📡 Sensor Readings</span><br style="margin-bottom:4px;">
  🌡️ Air: <strong style="color:#f1f5f9;">{weather['temperature_c']}°C</strong> &nbsp;|&nbsp;
  💧 Humidity: <strong style="color:#f1f5f9;">{weather['humidity_pct']}%</strong> &nbsp;|&nbsp;
  ☁️ <span style="color:#f1f5f9;">{weather['weather_condition']}</span> &nbsp;|&nbsp;
  🌬️ Wind: <strong style="color:#f1f5f9;">{weather['wind_speed_ms']} m/s</strong>
</div>

<div style="background:rgba(59,130,246,0.15);border:1px solid rgba(96,165,250,0.4);border-radius:8px;padding:12px;margin-bottom:10px;color:#bfdbfe;">
  <strong style="color:#93c5fd;">⚡ Recommended Action</strong><br>
  <span style="font-size:0.9rem;color:#e0f2fe;">{result.get('recommended_action', '')}</span>
</div>

<div style="background:rgba(234,179,8,0.12);border:1px solid rgba(234,179,8,0.4);border-radius:8px;padding:12px;margin-bottom:10px;">
  <strong style="color:#fde047;">📱 WhatsApp Alert → Farmer</strong><br>
  <code style="font-size:0.85rem;color:#fef9c3;">{result.get('farmer_message', '')}</code>
</div>

<div style="background:rgba(34,197,94,0.12);border:1px solid rgba(34,197,94,0.35);border-radius:8px;padding:12px;margin-bottom:10px;">
  <strong style="color:#86efac;">📧 Email → Crop Buyers</strong><br>
  <pre style="font-size:0.82rem;white-space:pre-wrap;margin:6px 0 0;color:#d1fae5;font-family:inherit;">{result.get('buyer_message', '')}</pre>
</div>

<div style="background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:10px;font-size:0.82rem;color:#94a3b8;">
  🔍 <em>{result.get('key_concern', '')}</em>
</div>
"""


def render_demo(scenario_idx: int) -> str:
    s = DEMO_SCENARIOS[scenario_idx]
    soil_html = (
        f"<div style='background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);"
        f"border-radius:8px;padding:10px 12px;margin-bottom:10px;font-size:0.88rem;color:#e2e8f0;'>"
        f"<span style='color:#94a3b8;font-weight:600;'>🪱 Soil Sensors</span> &nbsp;|&nbsp; "
        f"💧 Moisture: <strong style='color:#f1f5f9;'>{s['soil']['moisture']}%</strong> &nbsp;|&nbsp; "
        f"🌡️ Soil Temp: <strong style='color:#f1f5f9;'>{s['soil']['temp']}°C</strong> &nbsp;|&nbsp; "
        f"⚗️ pH: <strong style='color:#f1f5f9;'>{s['soil']['ph']}</strong>"
        f"</div>"
    )
    return soil_html + render_result(s["result"], s["weather"], s["city"])


# ── Live analysis ────────────────────────────────────────────────────────────
def fetch_weather(city: str, api_key: str):
    if not api_key:
        return None, "No OpenWeatherMap key"
    try:
        r = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric",
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        return {
            "temperature_c":    round(d["main"]["temp"], 1),
            "humidity_pct":     d["main"]["humidity"],
            "weather_condition": d["weather"][0]["main"],
            "wind_speed_ms":    round(d["wind"]["speed"], 1),
            "location":         d["name"],
            "feels_like":       round(d["main"]["feels_like"], 1),
        }, None
    except Exception as e:
        return None, str(e)


def analyze_farm(city, soil_moisture, soil_temp, soil_ph, openai_key_input, owm_key_input):
    oai_key = openai_key_input.strip() or ENV_OPENAI_KEY
    owm_key = owm_key_input.strip() or ENV_OWM_KEY

    if not oai_key:
        return (
            "<div style='background:rgba(239,68,68,0.15);border:2px solid #ef4444;border-radius:10px;"
            "padding:16px;color:#fca5a5;'>"
            "<strong>❌ OpenAI API key required</strong><br>"
            "<small style='color:#fecaca;'>Enter it in the field above, or add <code>OPENAI_API_KEY</code> "
            "as a Secret in HF Space Settings → Variables and Secrets.</small></div>"
        )

    weather, err = fetch_weather(city.strip(), owm_key)
    weather_note = ""
    if not weather:
        weather = {
            "temperature_c": 25.0, "humidity_pct": 60.0,
            "weather_condition": "Unknown (demo)", "wind_speed_ms": 5.0,
            "location": city.strip(), "feels_like": 25.0,
        }
        weather_note = f"Live weather unavailable ({err}) — using demo weather values. Soil data is from your sliders."

    prompt = f"""Analyze these farm sensor readings. Detect any agricultural crisis.

Location: {weather['location']}
Temperature: {weather['temperature_c']}°C (feels like {weather.get('feels_like', weather['temperature_c'])}°C)
Humidity: {weather['humidity_pct']}%
Weather: {weather['weather_condition']}
Wind Speed: {weather['wind_speed_ms']} m/s
Soil Moisture: {soil_moisture}%
Soil Temperature: {soil_temp}°C
Soil pH: {soil_ph}
Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

Crisis thresholds:
- Drought: soil moisture < 20% AND humidity < 30%
- Frost: temperature < 2°C OR soil temp < 1°C
- Heat Stress: temperature > 38°C
- Flooding: soil moisture > 85%
- Storm: wind speed > 15 m/s

Return ONLY a JSON object:
{{
  "is_crisis": false,
  "crisis_type": "none",
  "severity": "low",
  "recommended_action": "...",
  "farmer_message": "...",
  "buyer_message": "...",
  "key_concern": "..."
}}
severity must be: low | medium | high | critical
farmer_message must be WhatsApp-ready (max 200 chars).
buyer_message must be a professional email body."""

    try:
        client = OpenAI(api_key=oai_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an agricultural crisis detection AI. Return only valid JSON."},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
    except Exception as e:
        return (
            f"<div style='background:#fee2e2;border:1px solid #ef4444;border-radius:8px;"
            f"padding:12px;color:#991b1b;'>❌ OpenAI error: {str(e)}</div>"
        )

    return render_result(result, weather, weather.get("location", city), weather_note)


# ── Gradio UI ────────────────────────────────────────────────────────────────
CSS = """
footer { display: none !important; }
.tab-nav button { font-size: 0.95rem !important; }
"""

with gr.Blocks(
    title="🌾 Smart Farm Crisis Response Agent",
    theme=gr.themes.Soft(primary_hue="green", secondary_hue="teal"),
    css=CSS,
) as demo:

    gr.HTML("""
    <div style="text-align:center;padding:1.5rem 0 0.75rem;">
      <h1 style="font-size:2rem;margin-bottom:0.2rem;">🌾 Smart Farm Crisis Response Agent</h1>
      <p style="color:#6b7280;font-size:0.95rem;margin:0;">
        Real-time AI detection of drought · frost · heat stress · flooding · storms
      </p>
      <p style="color:#9ca3af;font-size:0.82rem;margin-top:0.4rem;">
        GPT-4o-mini + OpenWeatherMap · mirrors the live n8n automation workflow
      </p>
    </div>
    """)

    with gr.Tabs():

        # ── Tab 1: Live Demo (no API key needed) ───────────────────────────
        with gr.Tab("🎮 Live Demo"):
            gr.HTML("""
            <div style="background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.4);
                        border-radius:8px;padding:12px 16px;margin-bottom:12px;
                        font-size:0.9rem;color:#86efac;">
              <strong>👇 No API key needed</strong> — click any scenario below to see the full AI output
            </div>
            """)

            demo_output = gr.HTML(label="")

            with gr.Row():
                for i, s in enumerate(DEMO_SCENARIOS):
                    btn = gr.Button(s["label"], size="sm")
                    btn.click(fn=lambda idx=i: render_demo(idx), outputs=demo_output)

        # ── Tab 2: Analyze (live API) ────────────────────────────────────
        with gr.Tab("🔍 Live Analyze"):
            with gr.Row():

                # Left — inputs
                with gr.Column(scale=1, min_width=300):
                    with gr.Group():
                        gr.Markdown("#### 🔑 API Keys")
                        openai_key_in = gr.Textbox(
                            label="OpenAI API Key",
                            placeholder="sk-... (or set OPENAI_API_KEY as HF Secret)",
                            type="password",
                        )
                        owm_key_in = gr.Textbox(
                            label="OpenWeatherMap API Key (optional)",
                            placeholder="Fetches live weather — leave blank to use demo weather",
                            type="password",
                        )

                    with gr.Group():
                        gr.Markdown("#### 📍 Farm Location")
                        city_in = gr.Textbox(
                            label="City / Region",
                            value="Fresno, CA",
                            placeholder="e.g. Fresno, CA  |  Mumbai  |  Nairobi",
                        )

                    with gr.Group():
                        gr.Markdown("#### 🪱 Soil Sensor Readings")
                        moisture_in = gr.Slider(label="Soil Moisture (%)",    minimum=0,   maximum=100, value=15,  step=1)
                        soiltemp_in = gr.Slider(label="Soil Temperature (°C)", minimum=-10, maximum=60,  value=28,  step=0.5)
                        ph_in       = gr.Slider(label="Soil pH",               minimum=3.0, maximum=10,  value=6.5, step=0.1)

                    gr.HTML("""
                    <div style="background:rgba(59,130,246,0.15);border:1px solid rgba(96,165,250,0.4);
                                border-radius:6px;padding:8px 12px;font-size:0.82rem;
                                color:#bfdbfe;margin-bottom:8px;">
                      💡 Default values simulate a <strong>drought scenario</strong>
                      (moisture 15%) — hit Analyze to see the AI in action.
                    </div>
                    """)

                    analyze_btn = gr.Button("🔍  Analyze Farm Conditions", variant="primary", size="lg")

                # Right — output
                with gr.Column(scale=1, min_width=300):
                    gr.Markdown("#### 📊 AI Analysis Output")
                    result_html = gr.HTML(
                        value="<div style='color:#9ca3af;padding:40px;text-align:center;'>"
                              "Results will appear here after analysis ⬅️</div>"
                    )

            analyze_btn.click(
                fn=analyze_farm,
                inputs=[city_in, moisture_in, soiltemp_in, ph_in, openai_key_in, owm_key_in],
                outputs=result_html,
            )

        # ── Tab 3: How It Works ──────────────────────────────────────────
        with gr.Tab("📖 How It Works"):
            gr.Markdown("""
## Architecture

This UI mirrors the live **n8n Smart Farm Crisis Response Agent** running every 15 min:

```
Schedule Trigger (every 15 min)
  → Fetch Weather  (OpenWeatherMap API)
  → Normalize Weather Data
  → Fetch Soil Sensor Data  (IoT / Ubidots endpoint)
  → Combine Sensor Data
  → GPT-4o-mini Analysis  (detect crisis type + severity)
  → Crisis Detected?
      ├── YES → WhatsApp Alert (Twilio) → Email Buyers (Gmail) → Trigger Irrigation
      └── NO  → Log All Clear
```

## Crisis Thresholds

| Crisis | Condition |
|--------|-----------|
| 🏜️ Drought | Soil moisture **< 20%** AND humidity **< 30%** |
| 🥶 Frost | Temperature **< 2°C** OR soil temp **< 1°C** |
| 🔥 Heat Stress | Temperature **> 38°C** |
| 🌊 Flooding Risk | Soil moisture **> 85%** |
| 🌪️ Storm Risk | Wind speed **> 15 m/s** |

## Severity Levels

| | Level | Meaning |
|--|-------|---------|
| 🟢 | Low | Within normal range |
| 🟡 | Medium | Watch closely |
| 🟠 | High | Immediate attention needed |
| 🔴 | Critical | Emergency — act now |

## Adding Your OpenAI Key to HF Spaces

1. Go to your Space → **Settings** tab
2. Scroll to **Variables and Secrets**
3. Click **New secret**
4. Name: `OPENAI_API_KEY` · Value: `sk-...`
5. Click **Save** — Space restarts automatically

Optionally add `OPENWEATHER_API_KEY` for live weather data.

## Links

- 🔗 [n8n Workflow](https://aravind5.app.n8n.cloud/workflow/3YhdfeaAg8uz8eEc)
- 🌦️ [Get OpenWeatherMap API Key (free)](https://openweathermap.org/api)
- 🤖 [Get OpenAI API Key](https://platform.openai.com/api-keys)
            """)

    gr.HTML("""
    <div style="text-align:center;color:#9ca3af;font-size:0.78rem;padding:1rem 0 0.5rem;">
      Smart Farm Crisis Response Agent · GPT-4o-mini + OpenWeatherMap + n8n
    </div>
    """)

if __name__ == "__main__":
    demo.launch(show_error=True)
