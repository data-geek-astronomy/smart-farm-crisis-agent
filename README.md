---
title: Smart Farm Crisis Response Agent
emoji: 🌾
colorFrom: green
colorTo: green
sdk: gradio
sdk_version: 5.9.1
app_file: app.py
pinned: false
license: mit
short_description: AI farm crisis detection for drought frost flooding
python_version: "3.10"
---

# 🌾 Smart Farm Crisis Response Agent

Real-time AI monitoring for agricultural crises using live weather data and soil sensor readings.

## What It Does

Detects 5 types of farm crises in real time:

| Crisis | Trigger |
|--------|---------|
| 🏜️ Drought | Soil moisture < 20% AND humidity < 30% |
| 🥶 Frost | Temperature < 2°C OR soil temp < 1°C |
| 🔥 Heat Stress | Temperature > 38°C |
| 🌊 Flooding Risk | Soil moisture > 85% |
| 🌪️ Storm Risk | Wind speed > 15 m/s |

## How To Use

1. Enter your **OpenAI API key** and **OpenWeatherMap API key** (or set them as Space Secrets)
2. Set your farm's city name
3. Enter soil sensor readings (moisture %, temperature, pH)
4. Click **Analyze Farm Conditions**

The agent returns:
- Crisis status and severity level
- Live weather data for your location
- WhatsApp-ready alert message for the farmer
- Professional email body for crop buyers
- Recommended action

## Architecture

This UI mirrors the live **n8n workflow** that runs automatically every 15 minutes:

```
Schedule Trigger → OpenWeatherMap → IoT Soil Sensors
  → GPT-4o-mini Analysis
    → Crisis? YES → Twilio WhatsApp + Gmail + Irrigation API
    → Crisis? NO  → Log All Clear
```

## Setup

### Environment Variables / Space Secrets

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `OPENWEATHER_API_KEY` | Your OpenWeatherMap API key (free tier works) |

### Local Development

```bash
git clone https://github.com/YOUR_USERNAME/smart-farm-crisis-agent
cd smart-farm-crisis-agent
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
export OPENWEATHER_API_KEY=...
python app.py
```

## Links

- 🔗 n8n Workflow: https://aravind5.app.n8n.cloud/workflow/3YhdfeaAg8uz8eEc
- 🌦️ OpenWeatherMap API: https://openweathermap.org/api
- 🤖 OpenAI API: https://platform.openai.com/api-keys
