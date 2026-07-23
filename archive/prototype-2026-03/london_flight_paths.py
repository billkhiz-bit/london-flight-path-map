"""
London Flight Path & Property Noise Analysis Map v2.0
=====================================================
Interactive map with:
  1. Airports, flight paths, noise zones (v1 features)
  2. Live flight tracking (OpenSky Network - free)
  3. Property prices per borough (Land Registry data)
  4. Transport links (Tube, Overground, Elizabeth Line)
  5. Noise vs Price value analysis
  6. Postcode/address search bar

Generates: london_flight_paths.html (open in any browser)
Re-run to refresh live flight positions.
"""

import folium
from folium import plugins
import json
import math
import urllib.request
import ssl
from datetime import datetime

# ============================================================
# DATA: London Airports
# ============================================================
AIRPORTS = {
    "Heathrow (LHR)": {
        "coords": [51.4700, -0.4543],
        "runways": [
            {"name": "09L/27R", "coords": [[51.4775, -0.4890], [51.4775, -0.4280]]},
            {"name": "09R/27L", "coords": [[51.4644, -0.4890], [51.4644, -0.4280]]},
        ],
        "type": "major",
        "passengers_m": 79.2,
        "info": "UK's busiest airport. Westerly ops ~70% of time. Arrivals approach from east over central London. Major noise source for west/southwest London.",
    },
    "Gatwick (LGW)": {
        "coords": [51.1537, -0.1821],
        "runways": [
            {"name": "08R/26L", "coords": [[51.1565, -0.2050], [51.1500, -0.1600]]},
        ],
        "type": "major",
        "passengers_m": 40.9,
        "info": "UK's 2nd busiest. South of London. Mainly affects areas directly north/south of runway. Less impact on central London.",
    },
    "London City (LCY)": {
        "coords": [51.5053, 0.0553],
        "runways": [
            {"name": "09/27", "coords": [[51.5053, 0.0440], [51.5053, 0.0670]]},
        ],
        "type": "city",
        "passengers_m": 5.1,
        "info": "Steep 5.5 degree approach. Affects Docklands, Greenwich, parts of southeast London. Smaller aircraft only. Curfew: no flights 12:30-06:30 Sat night/Sun, 22:00-06:30 weekdays.",
    },
    "Stansted (STN)": {
        "coords": [51.8860, 0.2389],
        "runways": [
            {"name": "04/22", "coords": [[51.8790, 0.2200], [51.8940, 0.2590]]},
        ],
        "type": "major",
        "passengers_m": 28.0,
        "info": "Northeast of London. Minimal impact on London proper due to distance (~30 miles). Mainly affects Essex/Herts corridor.",
    },
    "Luton (LTN)": {
        "coords": [51.8747, -0.3684],
        "runways": [
            {"name": "07/25", "coords": [[51.8747, -0.3900], [51.8747, -0.3470]]},
        ],
        "type": "major",
        "passengers_m": 16.8,
        "info": "Northwest of London. Affects north London suburbs on approach. Growing rapidly as budget airline hub.",
    },
    "Biggin Hill (BQH)": {
        "coords": [51.3308, 0.0325],
        "runways": [
            {"name": "03/21", "coords": [[51.3250, 0.0290], [51.3370, 0.0360]]},
        ],
        "type": "minor",
        "passengers_m": 0.05,
        "info": "Business aviation airport in Bromley. Low traffic volume. Minimal noise impact on surrounding area.",
    },
}

# ============================================================
# DATA: Flight Path Corridors
# ============================================================
FLIGHT_PATHS = {
    "LHR Arrival - Westerly via Lambourne (NE)": {
        "type": "arrival", "airport": "Heathrow", "frequency": "high",
        "coords": [
            [51.6500, 0.1500], [51.6200, 0.0800], [51.5900, 0.0200],
            [51.5650, -0.0400], [51.5400, -0.1000], [51.5200, -0.1800],
            [51.5050, -0.2500], [51.4950, -0.3200], [51.4850, -0.3800],
            [51.4775, -0.4280],
        ],
        "info": "Arrivals from northeast via Lambourne stack. Overflies east London, City, Westminster area.",
    },
    "LHR Arrival - Westerly via Biggin (S)": {
        "type": "arrival", "airport": "Heathrow", "frequency": "high",
        "coords": [
            [51.3300, 0.0300], [51.3500, -0.0200], [51.3700, -0.0600],
            [51.3900, -0.1100], [51.4100, -0.1600], [51.4250, -0.2200],
            [51.4400, -0.2800], [51.4500, -0.3400], [51.4600, -0.3900],
            [51.4644, -0.4280],
        ],
        "info": "Arrivals from south via Biggin stack. Overflies south London, Croydon, Wandsworth, Richmond.",
    },
    "LHR Arrival - Westerly via Ockham (SW)": {
        "type": "arrival", "airport": "Heathrow", "frequency": "high",
        "coords": [
            [51.2800, -0.4500], [51.3100, -0.4400], [51.3400, -0.4350],
            [51.3700, -0.4350], [51.4000, -0.4350], [51.4200, -0.4350],
            [51.4400, -0.4350], [51.4644, -0.4350],
        ],
        "info": "Arrivals from southwest via Ockham. Approach mostly over Surrey, less London impact.",
    },
    "LHR Arrival - Westerly via Bovingdon (NW)": {
        "type": "arrival", "airport": "Heathrow", "frequency": "high",
        "coords": [
            [51.7200, -0.5500], [51.6800, -0.5200], [51.6400, -0.5000],
            [51.6000, -0.4900], [51.5600, -0.4800], [51.5300, -0.4700],
            [51.5050, -0.4600], [51.4775, -0.4500],
        ],
        "info": "Arrivals from northwest via Bovingdon. Overflies northwest London suburbs.",
    },
    "LHR Arrival - Easterly (from West over Windsor)": {
        "type": "arrival", "airport": "Heathrow", "frequency": "medium",
        "coords": [
            [51.4800, -0.6500], [51.4790, -0.6000], [51.4785, -0.5500],
            [51.4780, -0.5000], [51.4775, -0.4890],
        ],
        "info": "Easterly arrivals from west. Overflies Windsor/Slough. Less impact on London.",
    },
    "LHR Departure - Westerly (Climb West)": {
        "type": "departure", "airport": "Heathrow", "frequency": "high",
        "coords": [
            [51.4775, -0.4890], [51.4800, -0.5500], [51.4850, -0.6200],
            [51.4900, -0.7000], [51.4950, -0.7800],
        ],
        "info": "Westerly departures climb out over Windsor/Berkshire. Less London impact.",
    },
    "LHR Departure - Easterly via Detling (SE)": {
        "type": "departure", "airport": "Heathrow", "frequency": "medium",
        "coords": [
            [51.4775, -0.4280], [51.4700, -0.3500], [51.4600, -0.2500],
            [51.4450, -0.1500], [51.4300, -0.0500], [51.4100, 0.0500],
            [51.3900, 0.1500],
        ],
        "info": "Easterly departures turning south over south London. Overflies Wandsworth, Lambeth, Lewisham.",
    },
    "LHR Departure - Easterly via BPK (NE)": {
        "type": "departure", "airport": "Heathrow", "frequency": "medium",
        "coords": [
            [51.4775, -0.4280], [51.4900, -0.3500], [51.5100, -0.2500],
            [51.5300, -0.1500], [51.5500, -0.0500], [51.5700, 0.0500],
            [51.5900, 0.1500],
        ],
        "info": "Easterly departures turning north over central/north London. Overflies Ealing, Hammersmith, City.",
    },
    "LCY Arrival - Westerly (from East over Thames)": {
        "type": "arrival", "airport": "London City", "frequency": "medium",
        "coords": [
            [51.4800, 0.2000], [51.4850, 0.1700], [51.4880, 0.1400],
            [51.4920, 0.1100], [51.4970, 0.0900], [51.5020, 0.0700],
            [51.5053, 0.0553],
        ],
        "info": "Steep approach following Thames. Affects Woolwich, Greenwich, Thamesmead.",
    },
    "LCY Arrival - Easterly (from West over Canary Wharf)": {
        "type": "arrival", "airport": "London City", "frequency": "medium",
        "coords": [
            [51.5200, -0.0200], [51.5170, -0.0050], [51.5130, 0.0100],
            [51.5100, 0.0250], [51.5080, 0.0400], [51.5053, 0.0553],
        ],
        "info": "Approach from west over Canary Wharf and Docklands area.",
    },
    "LCY Departure - Easterly": {
        "type": "departure", "airport": "London City", "frequency": "medium",
        "coords": [
            [51.5053, 0.0670], [51.5050, 0.0900], [51.5030, 0.1200],
            [51.4980, 0.1600], [51.4900, 0.2100],
        ],
        "info": "Departures heading east over Beckton, Barking, Thames estuary.",
    },
    "LGW Arrival - from North (over S London)": {
        "type": "arrival", "airport": "Gatwick", "frequency": "medium",
        "coords": [
            [51.3500, -0.1000], [51.3200, -0.1200], [51.2800, -0.1400],
            [51.2300, -0.1600], [51.1900, -0.1700], [51.1537, -0.1821],
        ],
        "info": "Arrivals from north can affect Croydon/Purley corridor down to Gatwick.",
    },
    "LGW Departure - Northbound (towards London)": {
        "type": "departure", "airport": "Gatwick", "frequency": "medium",
        "coords": [
            [51.1565, -0.1821], [51.1900, -0.1700], [51.2200, -0.1500],
            [51.2600, -0.1300], [51.3000, -0.1100], [51.3500, -0.0800],
        ],
        "info": "Departures northbound climb over Croydon/south London area.",
    },
    "LTN Arrival - from South (over N London)": {
        "type": "arrival", "airport": "Luton", "frequency": "medium",
        "coords": [
            [51.6000, -0.3000], [51.6500, -0.3200], [51.7000, -0.3400],
            [51.7500, -0.3500], [51.8000, -0.3600], [51.8747, -0.3684],
        ],
        "info": "Arrivals from south pass over Barnet, Finchley, north London suburbs.",
    },
}

# ============================================================
# DATA: Noise Impact Zones
# ============================================================
NOISE_ZONES = {
    "LHR - Severe Noise (>72 dB Lden)": {
        "color": "#d32f2f", "fill_opacity": 0.35,
        "coords": [
            [51.4900, -0.5100], [51.4900, -0.3800],
            [51.4800, -0.3600], [51.4650, -0.3600],
            [51.4550, -0.3800], [51.4550, -0.5100],
            [51.4650, -0.5200], [51.4800, -0.5200],
        ],
        "level": "severe",
        "info": "72+ dB Lden. Significant adverse impact. Conversation difficult outdoors. Constant awareness of aircraft. Areas: Hounslow, Cranford, Hatton, Harmondsworth, Sipson.",
    },
    "LHR - High Noise (63-72 dB Lden)": {
        "color": "#f57c00", "fill_opacity": 0.25,
        "coords": [
            [51.5050, -0.5600], [51.5100, -0.3200],
            [51.4950, -0.2800], [51.4800, -0.2600],
            [51.4600, -0.2600], [51.4450, -0.2800],
            [51.4350, -0.3200], [51.4350, -0.5600],
            [51.4450, -0.5800], [51.4600, -0.5900],
            [51.4800, -0.5900], [51.4950, -0.5800],
        ],
        "level": "high",
        "info": "63-72 dB Lden. Significant noise. Sleep disturbance likely with windows open. Areas: Feltham, Isleworth, Heston, Bedfont, Stanwell, Ashford, Sunbury.",
    },
    "LHR - Moderate Noise (57-63 dB Lden)": {
        "color": "#fdd835", "fill_opacity": 0.18,
        "coords": [
            [51.5200, -0.6200], [51.5300, -0.3000],
            [51.5150, -0.2200], [51.5000, -0.1800],
            [51.4800, -0.1600], [51.4500, -0.1600],
            [51.4300, -0.1800], [51.4150, -0.2200],
            [51.4050, -0.3000], [51.4000, -0.6200],
            [51.4150, -0.6600], [51.4300, -0.6800],
            [51.4500, -0.6900], [51.4800, -0.6900],
            [51.5000, -0.6800], [51.5100, -0.6600],
        ],
        "level": "moderate",
        "info": "57-63 dB Lden. Noticeable aircraft noise, especially outdoors. Areas: Twickenham, Richmond, Brentford, Ealing (parts), Osterley, Staines, Weybridge.",
    },
    "LHR - Noticeable Noise (51-57 dB Lden)": {
        "color": "#a5d6a7", "fill_opacity": 0.15,
        "coords": [
            [51.5400, -0.2000], [51.5500, -0.0500],
            [51.5400, 0.0500], [51.5200, 0.1000],
            [51.4800, 0.1000], [51.4600, 0.0500],
            [51.4500, -0.0500], [51.4500, -0.2000],
        ],
        "level": "low",
        "info": "51-57 dB Lden. Arrival corridor noise. Planes at 2000-5000ft. Noticeable but not dominant. Areas: Wandsworth, Battersea, Clapham, Brixton (variable by day).",
    },
    "LCY - Moderate Noise Zone": {
        "color": "#f57c00", "fill_opacity": 0.2,
        "coords": [
            [51.5150, 0.0300], [51.5150, 0.0800],
            [51.5050, 0.1000], [51.4950, 0.1000],
            [51.4900, 0.0800], [51.4900, 0.0300],
            [51.4950, 0.0200], [51.5050, 0.0200],
        ],
        "level": "moderate",
        "info": "London City noise zone. Steep approaches mean concentrated but intense noise in narrow corridor. Curfew helps.",
    },
}

# ============================================================
# DATA: Borough info with noise impact AND property prices
# Prices: avg property price (2024/2025 Land Registry + ONS data)
# ============================================================
BOROUGH_DATA = {
    "Hounslow": {
        "coords": [51.4688, -0.3614], "impact": "severe",
        "avg_price": 465000, "price_trend": "+3.2%",
        "note": "Most affected borough. Directly under Heathrow flight paths. Western parts extremely noisy.",
        "property_note": "Prices suppressed by noise. Good value vs neighbours. Chiswick end much pricier.",
    },
    "Hillingdon": {
        "coords": [51.5353, -0.4497], "impact": "severe",
        "avg_price": 480000, "price_trend": "+2.8%",
        "note": "Heathrow is in Hillingdon. Northern areas quieter, but south severely affected.",
        "property_note": "North (Ruislip, Ickenham) = quiet + good value. South = noise discount.",
    },
    "Richmond upon Thames": {
        "coords": [51.4613, -0.3037], "impact": "high",
        "avg_price": 825000, "price_trend": "+1.5%",
        "note": "Under arrival/departure paths. Beautiful area but significant aircraft noise, especially in east.",
        "property_note": "Premium despite noise. River views + parks justify prices. Noise = bargaining leverage.",
    },
    "Ealing": {
        "coords": [51.5130, -0.3089], "impact": "high",
        "avg_price": 540000, "price_trend": "+4.1%",
        "note": "Southern Ealing under Heathrow paths. Southall particularly affected. North Ealing much quieter.",
        "property_note": "Elizabeth Line boosted north Ealing. South = affordable but noisy. Great value in Hanwell.",
    },
    "Wandsworth": {
        "coords": [51.4567, -0.1910], "impact": "moderate",
        "avg_price": 680000, "price_trend": "+2.1%",
        "note": "Under Heathrow approach corridor at higher altitude. Intermittent noise from arrivals.",
        "property_note": "Battersea regeneration driving prices. Tooting = best value. Putney premium.",
    },
    "Lambeth": {
        "coords": [51.4571, -0.1231], "impact": "moderate",
        "avg_price": 560000, "price_trend": "+3.5%",
        "note": "Heathrow arrivals pass over at ~4000ft. Noticeable on quiet days.",
        "property_note": "Brixton gentrifying fast. Streatham = family-friendly value. Waterloo end = premium.",
    },
    "Lewisham": {
        "coords": [51.4415, -0.0117], "impact": "low-moderate",
        "avg_price": 445000, "price_trend": "+4.8%",
        "note": "Some London City traffic. Heathrow arrivals at altitude. Generally acceptable.",
        "property_note": "One of best value inner-London boroughs. Ladywell, Brockley = popular. Bakerloo extension potential.",
    },
    "Greenwich": {
        "coords": [51.4892, 0.0648], "impact": "moderate",
        "avg_price": 430000, "price_trend": "+5.2%",
        "note": "London City Airport approach corridor. Steep approach concentrates noise.",
        "property_note": "Woolwich Elizabeth Line = price boost. Blackheath = premium. Good growth area.",
    },
    "Tower Hamlets": {
        "coords": [51.5203, -0.0293], "impact": "low-moderate",
        "avg_price": 495000, "price_trend": "+2.0%",
        "note": "Some London City traffic. Canary Wharf area can hear LCY approaches.",
        "property_note": "Canary Wharf oversupply = deals. Bow, Mile End = better value. Wapping = premium.",
    },
    "Camden": {
        "coords": [51.5517, -0.1588], "impact": "low",
        "avg_price": 780000, "price_trend": "+1.2%",
        "note": "Relatively quiet from aircraft. Not under major flight paths.",
        "property_note": "Premium borough. Kentish Town = relative value. Hampstead = ultra-premium. Quiet skies = selling point.",
    },
    "Islington": {
        "coords": [51.5465, -0.1058], "impact": "low",
        "avg_price": 720000, "price_trend": "+1.8%",
        "note": "Minimal aircraft impact. Well away from major approach corridors.",
        "property_note": "Desirable + quiet. Holloway = entry point. Angel/Upper St = premium. Good schools.",
    },
    "Hackney": {
        "coords": [51.5450, -0.0553], "impact": "low",
        "avg_price": 590000, "price_trend": "+3.0%",
        "note": "Generally quiet from aircraft. Not under major approach paths.",
        "property_note": "Creative hub. Dalston, Hackney Central gentrified. Clapton = next wave. Quiet skies.",
    },
    "Barnet": {
        "coords": [51.6252, -0.1517], "impact": "low-moderate",
        "avg_price": 560000, "price_trend": "+3.1%",
        "note": "Some Luton arrivals pass over. Generally at altitude.",
        "property_note": "Suburban feel. Good schools. East Finchley, Friern Barnet = value. Mill Hill = premium.",
    },
    "Croydon": {
        "coords": [51.3762, -0.0986], "impact": "moderate",
        "avg_price": 395000, "price_trend": "+4.5%",
        "note": "Under Gatwick departure/arrival corridor and Heathrow Biggin approach.",
        "property_note": "Most affordable in London. Major regeneration. Tram links. South Croydon = nicer. Best first-buyer borough.",
    },
    "Bromley": {
        "coords": [51.4039, 0.0198], "impact": "low",
        "avg_price": 480000, "price_trend": "+3.8%",
        "note": "Biggin Hill (minor airport) nearby but low traffic. Generally quiet.",
        "property_note": "Excellent schools. Suburban. Chislehurst = premium. Penge, Anerley = affordable entry.",
    },
    "Newham": {
        "coords": [51.5077, 0.0469], "impact": "moderate-high",
        "avg_price": 410000, "price_trend": "+5.8%",
        "note": "London City Airport is here. Areas near airport significantly affected.",
        "property_note": "Fastest growth in London. Stratford Olympic legacy. Elizabeth Line. Avoid Royal Docks for noise. Best for capital growth.",
    },
    "Southwark": {
        "coords": [51.4733, -0.0734], "impact": "low-moderate",
        "avg_price": 530000, "price_trend": "+2.5%",
        "note": "Under some Heathrow approach paths at altitude. Generally acceptable.",
        "property_note": "SE1 = premium (river). Peckham, Camberwell = value + culture. Canada Water regeneration.",
    },
    "Hammersmith & Fulham": {
        "coords": [51.4927, -0.2339], "impact": "moderate-high",
        "avg_price": 750000, "price_trend": "+1.0%",
        "note": "Under Heathrow easterly departure paths. Planes at lower altitude.",
        "property_note": "Fulham = premium. Shepherd's Bush = value. White City regeneration. Noise = bargaining point.",
    },
    "Kensington & Chelsea": {
        "coords": [51.4990, -0.1938], "impact": "moderate",
        "avg_price": 1350000, "price_trend": "+0.5%",
        "note": "Under some Heathrow paths at medium altitude. Intermittent but noticeable.",
        "property_note": "London's most expensive. North Kensington = relative value. Noise rarely affects prices here.",
    },
    "Brent": {
        "coords": [51.5588, -0.2517], "impact": "low-moderate",
        "avg_price": 490000, "price_trend": "+4.0%",
        "note": "Some Heathrow departure paths at altitude. Wembley area occasionally affected.",
        "property_note": "Wembley Park regeneration. Kilburn = Uber-accessible to centre. Queens Park = premium. Good transport.",
    },
    "Haringey": {
        "coords": [51.5906, -0.1110], "impact": "low",
        "avg_price": 545000, "price_trend": "+3.5%",
        "note": "Well away from all major flight corridors. Minimal aircraft noise.",
        "property_note": "Crouch End = premium no-tube village. Tottenham = regeneration + Spurs stadium. Wood Green = value.",
    },
    "Waltham Forest": {
        "coords": [51.5886, -0.0118], "impact": "low",
        "avg_price": 480000, "price_trend": "+4.2%",
        "note": "No significant aircraft noise. Well away from all airport approaches.",
        "property_note": "Borough of Culture legacy. Walthamstow Village = trendy. Leyton = affordable. Marshes = green space. Quiet skies.",
    },
    "Merton": {
        "coords": [51.4098, -0.1949], "impact": "low-moderate",
        "avg_price": 560000, "price_trend": "+2.8%",
        "note": "Some Heathrow paths at high altitude. Wimbledon Common buffers noise.",
        "property_note": "Wimbledon = premium. Mitcham, Morden = affordable. Colliers Wood = up and coming. Tram access.",
    },
    "Redbridge": {
        "coords": [51.5763, 0.0454], "impact": "low",
        "avg_price": 445000, "price_trend": "+3.9%",
        "note": "Away from main corridors. Lambourne stack passes north at high altitude.",
        "property_note": "Family borough. South Woodford = leafy. Ilford = Elizabeth Line boost. Wanstead = premium. Good value.",
    },
    "Enfield": {
        "coords": [51.6538, -0.0799], "impact": "low",
        "avg_price": 430000, "price_trend": "+4.3%",
        "note": "Far from all airport flight paths. Quiet skies across the borough.",
        "property_note": "Affordable north London. Enfield Town = nice centre. Palmers Green = Greek community. Lots of green space.",
    },
    "Kingston upon Thames": {
        "coords": [51.3925, -0.3057], "impact": "low-moderate",
        "avg_price": 550000, "price_trend": "+2.0%",
        "note": "Some Heathrow Ockham arrivals pass to the north. Generally quiet.",
        "property_note": "Riverside town feel. Good schools. Surbiton = commuter favourite. New Malden = Korean community + value.",
    },
    "Sutton": {
        "coords": [51.3618, -0.1945], "impact": "low",
        "avg_price": 415000, "price_trend": "+3.5%",
        "note": "Between Heathrow and Gatwick corridors but not directly under either.",
        "property_note": "Excellent schools (grammar). Carshalton = village feel. Cheam = family favourite. Very affordable for quality.",
    },
}

IMPACT_COLORS = {
    "severe": "#d32f2f", "high": "#f57c00", "moderate-high": "#ff9800",
    "moderate": "#fdd835", "low-moderate": "#a5d6a7", "low": "#4caf50",
}

# ============================================================
# DATA: London Transport Stations
# Major Tube, Overground, and Elizabeth Line stations
# ============================================================
TUBE_STATIONS = [
    # Central London interchange hubs
    {"name": "King's Cross St Pancras", "coords": [51.5308, -0.1238], "lines": "6 lines + HS1 + Thameslink", "zone": 1},
    {"name": "Bank / Monument", "coords": [51.5133, -0.0886], "lines": "Central, Northern, W&C, Circle, District, DLR", "zone": 1},
    {"name": "Oxford Circus", "coords": [51.5152, -0.1418], "lines": "Bakerloo, Central, Victoria", "zone": 1},
    {"name": "Victoria", "coords": [51.4965, -0.1447], "lines": "Victoria, Circle, District + National Rail", "zone": 1},
    {"name": "Liverpool Street", "coords": [51.5178, -0.0823], "lines": "Central, Circle, H&C, Metropolitan, Elizabeth", "zone": 1},
    {"name": "Waterloo", "coords": [51.5036, -0.1143], "lines": "Bakerloo, Jubilee, Northern, W&C + National Rail", "zone": 1},
    {"name": "Paddington", "coords": [51.5154, -0.1755], "lines": "Bakerloo, Circle, District, H&C, Elizabeth + GWR/Heathrow Express", "zone": 1},
    {"name": "London Bridge", "coords": [51.5052, -0.0864], "lines": "Jubilee, Northern + National Rail", "zone": 1},
    # Key Zone 2 stations
    {"name": "Stratford", "coords": [51.5416, -0.0033], "lines": "Central, Jubilee, Elizabeth, DLR, Overground", "zone": 3},
    {"name": "Canary Wharf", "coords": [51.5054, -0.0235], "lines": "Jubilee, Elizabeth, DLR", "zone": 2},
    {"name": "Brixton", "coords": [51.4627, -0.1145], "lines": "Victoria", "zone": 2},
    {"name": "Clapham Junction", "coords": [51.4641, -0.1703], "lines": "Overground + National Rail (busiest station)", "zone": 2},
    {"name": "Finsbury Park", "coords": [51.5642, -0.1065], "lines": "Victoria, Piccadilly + National Rail", "zone": 2},
    {"name": "Hammersmith", "coords": [51.4927, -0.2227], "lines": "Piccadilly, District, Circle, H&C", "zone": 2},
    # Key outer stations
    {"name": "Wimbledon", "coords": [51.4214, -0.2064], "lines": "District + Tramlink + National Rail", "zone": 3},
    {"name": "Richmond", "coords": [51.4632, -0.3013], "lines": "District, Overground + National Rail", "zone": 4},
    {"name": "Ealing Broadway", "coords": [51.5150, -0.3019], "lines": "Central, District, Elizabeth", "zone": 3},
    {"name": "Wembley Park", "coords": [51.5635, -0.2795], "lines": "Jubilee, Metropolitan", "zone": 4},
    {"name": "Woolwich (Elizabeth Line)", "coords": [51.4917, 0.0714], "lines": "Elizabeth Line", "zone": 4},
    {"name": "Tottenham Hale", "coords": [51.5882, -0.0602], "lines": "Victoria + National Rail + Stansted Express", "zone": 3},
    {"name": "East Croydon", "coords": [51.3753, -0.0927], "lines": "National Rail (Thameslink, Southern, Gatwick Express) + Tramlink", "zone": 5},
    {"name": "Lewisham", "coords": [51.4657, -0.0142], "lines": "DLR + National Rail", "zone": 3},
    {"name": "Blackheath", "coords": [51.4656, 0.0090], "lines": "National Rail (Southeastern)", "zone": 3},
    {"name": "Peckham Rye", "coords": [51.4700, -0.0693], "lines": "Overground + National Rail", "zone": 2},
    {"name": "Denmark Hill", "coords": [51.4684, -0.0891], "lines": "Overground + National Rail (Thameslink)", "zone": 2},
    {"name": "Highbury & Islington", "coords": [51.5463, -0.1040], "lines": "Victoria, Overground", "zone": 2},
    {"name": "Dalston Junction", "coords": [51.5462, -0.0753], "lines": "Overground", "zone": 2},
    {"name": "Walthamstow Central", "coords": [51.5830, -0.0197], "lines": "Victoria, Overground", "zone": 3},
    {"name": "Forest Hill", "coords": [51.4393, -0.0535], "lines": "Overground + National Rail", "zone": 3},
    {"name": "Crystal Palace", "coords": [51.4180, -0.0726], "lines": "Overground + National Rail", "zone": 4},
    {"name": "Ilford (Elizabeth Line)", "coords": [51.5590, 0.0708], "lines": "Elizabeth Line", "zone": 4},
    {"name": "Romford (Elizabeth Line)", "coords": [51.5750, 0.1835], "lines": "Elizabeth Line", "zone": 6},
    {"name": "Abbey Wood (Elizabeth Line)", "coords": [51.4910, 0.1203], "lines": "Elizabeth Line", "zone": 4},
    {"name": "Hounslow Central", "coords": [51.4713, -0.3665], "lines": "Piccadilly", "zone": 4},
    {"name": "Heathrow Terminals", "coords": [51.4713, -0.4524], "lines": "Piccadilly, Elizabeth Line, Heathrow Express", "zone": 6},
]

# ============================================================
# DATA: Quiet Zones and Tips (carried over from v1)
# ============================================================
QUIET_AREAS = [
    {"name": "Hampstead / Highgate", "coords": [51.5630, -0.1650],
     "note": "Leafy, elevated area. Well away from all major flight paths. Excellent for noise-sensitive buyers. Premium prices."},
    {"name": "Dulwich / Forest Hill", "coords": [51.4400, -0.0700],
     "note": "South London green corridor. Not under major flight paths. Good schools, parks, and relative quiet."},
    {"name": "Muswell Hill / Crouch End", "coords": [51.5900, -0.1400],
     "note": "North London heights. Minimal aircraft noise. Well away from Heathrow and City corridors."},
    {"name": "Walthamstow / Leyton", "coords": [51.5830, -0.0200],
     "note": "East London but away from LCY paths. Marshes provide green buffer. Increasingly popular, good value."},
    {"name": "Blackheath / Eltham", "coords": [51.4600, 0.0200],
     "note": "Southeast London. Away from major corridors. Blackheath village is particularly peaceful."},
    {"name": "Wimbledon / Merton", "coords": [51.4220, -0.2000],
     "note": "Some Heathrow paths at altitude but generally quiet. Common provides green space buffer."},
    {"name": "Peckham / Camberwell", "coords": [51.4700, -0.0800],
     "note": "Not under primary flight paths. Gentrifying rapidly. Good transport links. Relatively quiet skies."},
    {"name": "Stoke Newington / Dalston", "coords": [51.5610, -0.0750],
     "note": "Trendy northeast London. No significant aircraft noise. Canal-side living available."},
    {"name": "Wanstead / South Woodford", "coords": [51.5760, 0.0290],
     "note": "Leafy east London. Epping Forest nearby. Quiet skies. Central Line access. Family-friendly."},
    {"name": "Surbiton / New Malden", "coords": [51.3940, -0.3050],
     "note": "Southwest London suburbs. Fast trains to Waterloo. Away from flight paths. Village atmosphere."},
]

PROPERTY_TIPS = [
    {"name": "TIP: Check Time of Day", "coords": [51.55, -0.42],
     "tip": "Heathrow alternates runways. Westerly ops (most common): arrivals from EAST, departures WEST. Visit properties at different times - noise varies hugely between morning and evening."},
    {"name": "TIP: Altitude Matters", "coords": [51.55, -0.15],
     "tip": "Planes at 2000ft are MUCH louder than at 5000ft. Near airports = low planes. 10-15 miles out = 3000-4000ft. Beyond 15 miles = 5000ft+ and much less noticeable."},
    {"name": "TIP: Check WebTrak", "coords": [51.45, -0.08],
     "tip": "Heathrow's WebTrak (webtrak.emsbk.com/lhr6) shows REAL flight tracks. Check for any property. Also City Airport (webtrak.emsbk.com/lcy5). Free tools - bookmark them."},
    {"name": "TIP: Insulation Schemes", "coords": [51.47, -0.52],
     "tip": "Heathrow offers noise insulation for worst-affected areas. Check eligibility for free/subsidised double glazing. Offsets indoor noise but won't help gardens."},
    {"name": "TIP: Future Expansion", "coords": [51.50, -0.48],
     "tip": "A 3rd Heathrow runway (NW of current site) was approved but stalled. If built, noise patterns would change significantly. Check planning status before buying in Hillingdon/Hounslow."},
    {"name": "TIP: Respite & Alternation", "coords": [51.48, -0.30],
     "tip": "Heathrow operates runway alternation - each runway gets a break. Properties north of Heathrow get half-day respite. Check which alternation pattern affects your target area."},
    {"name": "TIP: Noise vs Price Sweet Spots", "coords": [51.44, -0.01],
     "tip": "Best value quiet areas: Lewisham, Waltham Forest, Croydon (south), Sutton, Enfield. Quiet skies + affordable + good transport. Worst noise-to-price: Hounslow, Feltham (noisy AND not cheap enough to compensate)."},
    {"name": "TIP: Elizabeth Line Effect", "coords": [51.52, -0.01],
     "tip": "Elizabeth Line stations (Abbey Wood, Woolwich, Forest Gate, Ilford) are seeing 10-20% price uplifts. Some of these areas also have quiet skies. Double benefit."},
]


def fetch_live_flights():
    """Fetch live aircraft positions over London from OpenSky Network (free API)."""
    url = "https://opensky-network.org/api/states/all?lamin=51.25&lomin=-0.65&lamax=51.75&lomax=0.30"
    print("Fetching live flight data from OpenSky Network...")
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "LondonFlightMap/2.0"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            data = json.loads(resp.read().decode())
        states = data.get("states", [])
        flights = []
        for s in states:
            if s[5] is not None and s[6] is not None:  # has lat/lon
                flights.append({
                    "callsign": (s[1] or "").strip(),
                    "origin": s[2] or "??",
                    "lat": s[6],
                    "lon": s[5],
                    "alt_m": s[7] or 0,  # barometric altitude
                    "velocity": s[9] or 0,  # m/s
                    "heading": s[10] or 0,
                    "on_ground": s[8],
                    "vert_rate": s[11] or 0,  # m/s, negative = descending
                })
        print(f"  Found {len(flights)} aircraft over London area")
        return flights
    except Exception as e:
        print(f"  Could not fetch live data: {e}")
        print("  Map will be generated without live flights (all other features work)")
        return []


def get_value_score(borough_data):
    """Calculate noise-adjusted value score. Higher = better value for quiet living."""
    impact_scores = {"low": 5, "low-moderate": 4, "moderate": 3, "moderate-high": 2, "high": 1, "severe": 0}
    noise_score = impact_scores.get(borough_data["impact"], 2)
    # Normalize price: cheaper = better score (inverse, scaled 0-5)
    price = borough_data["avg_price"]
    price_score = max(0, min(5, (1400000 - price) / 250000))
    # Growth bonus
    trend = float(borough_data["price_trend"].replace("%", "").replace("+", ""))
    growth_score = min(2, trend / 3)
    return round(noise_score * 1.5 + price_score + growth_score, 1)


def create_map():
    """Build the interactive London flight path + property map."""

    # Fetch live flights
    live_flights = fetch_live_flights()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    m = folium.Map(location=[51.5074, -0.1278], zoom_start=11, tiles=None, control_scale=True)

    # Base tile layers
    folium.TileLayer("OpenStreetMap", name="Street Map").add_to(m)
    folium.TileLayer("CartoDB positron", name="Light (Clean)").add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="Dark Mode").add_to(m)

    # Feature groups
    airports_layer = folium.FeatureGroup(name="1. Airports & Runways", show=True)
    arrivals_layer = folium.FeatureGroup(name="2. Arrival Paths", show=True)
    departures_layer = folium.FeatureGroup(name="3. Departure Paths", show=True)
    noise_layer = folium.FeatureGroup(name="4. Noise Zones", show=True)
    live_layer = folium.FeatureGroup(name="5. Live Flights (snapshot)", show=True)
    borough_layer = folium.FeatureGroup(name="6. Borough Noise + Prices", show=False)
    value_layer = folium.FeatureGroup(name="7. Value Score Heatmap", show=False)
    transport_layer = folium.FeatureGroup(name="8. Transport Links", show=False)
    quiet_layer = folium.FeatureGroup(name="9. Quiet Zones", show=False)
    tips_layer = folium.FeatureGroup(name="10. Property Tips", show=False)

    # ============================================================
    # AIRPORTS & RUNWAYS
    # ============================================================
    for name, data in AIRPORTS.items():
        icon_color = "red" if data["type"] == "major" else ("orange" if data["type"] == "city" else "gray")
        popup_html = f"""
        <div style="width:280px;font-family:Arial,sans-serif;">
            <h3 style="margin:0 0 8px;color:#1a237e;">{name}</h3>
            <p style="margin:0 0 5px;"><b>Passengers:</b> {data['passengers_m']}M/year</p>
            <p style="margin:0;font-size:13px;color:#555;">{data['info']}</p>
        </div>"""
        folium.Marker(
            location=data["coords"], popup=folium.Popup(popup_html, max_width=300),
            tooltip=name, icon=folium.Icon(color=icon_color, icon="plane", prefix="fa"),
        ).add_to(airports_layer)
        for rwy in data["runways"]:
            folium.PolyLine(
                locations=rwy["coords"], color="#333", weight=6, opacity=0.9,
                tooltip=f"{name} - Runway {rwy['name']}",
            ).add_to(airports_layer)

    # ============================================================
    # FLIGHT PATHS
    # ============================================================
    for path_name, data in FLIGHT_PATHS.items():
        is_arrival = data["type"] == "arrival"
        layer = arrivals_layer if is_arrival else departures_layer
        color = "#2196F3" if is_arrival else "#E91E63"
        weight = 4 if data["frequency"] == "high" else 3
        dash = None if data["frequency"] == "high" else "10 6"
        popup_html = f"""
        <div style="width:260px;font-family:Arial,sans-serif;">
            <h4 style="margin:0 0 5px;color:{'#1565C0' if is_arrival else '#C2185B'};">{path_name}</h4>
            <p style="margin:0 0 3px;"><b>Type:</b> {'Arrival' if is_arrival else 'Departure'} | <b>Freq:</b> {data['frequency'].title()}</p>
            <p style="margin:0;font-size:13px;color:#555;">{data['info']}</p>
        </div>"""
        folium.PolyLine(
            locations=data["coords"], color=color, weight=weight, opacity=0.7,
            dash_array=dash, popup=folium.Popup(popup_html, max_width=280), tooltip=path_name,
        ).add_to(layer)
        if len(data["coords"]) >= 2:
            mid = data["coords"][len(data["coords"]) // 2]
            arrow = "&#9660;" if is_arrival else "&#9650;"
            label = path_name.split(" - ")[1][:25] if " - " in path_name else path_name[:25]
            folium.Marker(
                location=mid,
                icon=folium.DivIcon(
                    html=f'<div style="font-size:10px;color:{color};font-weight:bold;white-space:nowrap;">{arrow} {label}</div>',
                    icon_size=(180, 20), icon_anchor=(90, 10),
                ),
            ).add_to(layer)

    # ============================================================
    # NOISE ZONES
    # ============================================================
    for zone_name, data in NOISE_ZONES.items():
        popup_html = f"""
        <div style="width:280px;font-family:Arial,sans-serif;">
            <h4 style="margin:0 0 5px;color:{data['color']};">{zone_name}</h4>
            <p style="margin:0;font-size:13px;">{data['info']}</p>
        </div>"""
        folium.Polygon(
            locations=data["coords"], color=data["color"], fill_color=data["color"],
            fill_opacity=data["fill_opacity"], weight=2, opacity=0.6,
            popup=folium.Popup(popup_html, max_width=300), tooltip=zone_name,
        ).add_to(noise_layer)

    # ============================================================
    # LIVE FLIGHTS
    # ============================================================
    for f in live_flights:
        if f["on_ground"]:
            continue
        alt_ft = int(f["alt_m"] * 3.281)
        speed_kts = int(f["velocity"] * 1.944)
        status = "Descending" if f["vert_rate"] < -1 else ("Climbing" if f["vert_rate"] > 1 else "Level")
        # Color by altitude
        if alt_ft < 3000:
            ac_color = "#d32f2f"  # red = low = loud
            ac_size = 8
        elif alt_ft < 6000:
            ac_color = "#f57c00"  # orange
            ac_size = 7
        elif alt_ft < 15000:
            ac_color = "#fdd835"  # yellow
            ac_size = 6
        else:
            ac_color = "#4caf50"  # green = high = quiet
            ac_size = 5

        popup_html = f"""
        <div style="width:220px;font-family:Arial,sans-serif;">
            <h4 style="margin:0 0 5px;">{f['callsign'] or 'Unknown'}</h4>
            <p style="margin:0;"><b>Altitude:</b> {alt_ft:,} ft</p>
            <p style="margin:0;"><b>Speed:</b> {speed_kts} kts</p>
            <p style="margin:0;"><b>Heading:</b> {int(f['heading'])}&deg;</p>
            <p style="margin:0;"><b>Status:</b> {status}</p>
            <p style="margin:0;"><b>Origin:</b> {f['origin']}</p>
            <p style="margin:3px 0 0;font-size:11px;color:#888;">Lower altitude = louder on ground</p>
        </div>"""
        folium.CircleMarker(
            location=[f["lat"], f["lon"]], radius=ac_size,
            color=ac_color, fill_color=ac_color, fill_opacity=0.85, weight=1,
            popup=folium.Popup(popup_html, max_width=240),
            tooltip=f"{f['callsign'] or '?'} | {alt_ft:,}ft | {status}",
        ).add_to(live_layer)

    # Timestamp label for live flights
    if live_flights:
        folium.Marker(
            location=[51.72, 0.22],
            icon=folium.DivIcon(
                html=f'<div style="font-size:11px;color:#666;background:rgba(255,255,255,0.8);padding:3px 6px;border-radius:4px;white-space:nowrap;">Live flights: {timestamp} (re-run script to refresh)</div>',
                icon_size=(280, 24), icon_anchor=(0, 12),
            ),
        ).add_to(live_layer)

    # ============================================================
    # BOROUGH NOISE + PROPERTY PRICES
    # ============================================================
    for borough, data in BOROUGH_DATA.items():
        color = IMPACT_COLORS.get(data["impact"], "#9e9e9e")
        value = get_value_score(data)
        price_k = data["avg_price"] // 1000

        popup_html = f"""
        <div style="width:320px;font-family:Arial,sans-serif;">
            <h4 style="margin:0 0 5px;">{borough}</h4>
            <table style="width:100%;font-size:13px;border-collapse:collapse;">
                <tr><td style="padding:2px 0;"><b>Noise Impact:</b></td>
                    <td><span style="background:{color};padding:2px 8px;border-radius:3px;font-weight:bold;">{data['impact'].upper()}</span></td></tr>
                <tr><td style="padding:2px 0;"><b>Avg Price:</b></td><td>&pound;{data['avg_price']:,}</td></tr>
                <tr><td style="padding:2px 0;"><b>Price Trend:</b></td><td>{data['price_trend']} (annual)</td></tr>
                <tr><td style="padding:2px 0;"><b>Value Score:</b></td><td><b>{value}/10</b> (noise-adjusted)</td></tr>
            </table>
            <p style="margin:6px 0 3px;font-size:12px;color:#555;"><b>Noise:</b> {data['note']}</p>
            <p style="margin:0;font-size:12px;color:#1565c0;"><b>Property:</b> {data['property_note']}</p>
        </div>"""

        folium.CircleMarker(
            location=data["coords"], radius=14,
            color=color, fill_color=color, fill_opacity=0.7, weight=2,
            popup=folium.Popup(popup_html, max_width=340),
            tooltip=f"{borough}: {data['impact'].upper()} | ~{price_k}k | Value: {value}/10",
        ).add_to(borough_layer)

        folium.Marker(
            location=data["coords"],
            icon=folium.DivIcon(
                html=f'<div style="font-size:9px;font-weight:bold;color:#333;text-align:center;white-space:nowrap;text-shadow:1px 1px 2px white,-1px -1px 2px white;">{borough}<br>&pound;{price_k}k</div>',
                icon_size=(130, 26), icon_anchor=(65, 13),
            ),
        ).add_to(borough_layer)

    # ============================================================
    # VALUE SCORE HEATMAP
    # ============================================================
    value_data = []
    for borough, data in BOROUGH_DATA.items():
        score = get_value_score(data)
        value_data.append([data["coords"][0], data["coords"][1], score])
        # Value label marker
        folium.Marker(
            location=data["coords"],
            icon=folium.DivIcon(
                html=f'<div style="font-size:12px;font-weight:bold;color:#1a237e;text-align:center;background:rgba(255,255,255,0.85);padding:1px 5px;border-radius:10px;border:2px solid {"#4caf50" if score >= 7 else "#f57c00" if score >= 5 else "#d32f2f"};white-space:nowrap;">{score}</div>',
                icon_size=(40, 22), icon_anchor=(20, 11),
            ),
            tooltip=f"{borough}: Value Score {score}/10",
        ).add_to(value_layer)

    plugins.HeatMap(
        value_data, name="Value Heatmap Overlay",
        min_opacity=0.3, radius=40, blur=30,
        gradient={0.2: '#d32f2f', 0.4: '#f57c00', 0.6: '#fdd835', 0.8: '#a5d6a7', 1.0: '#2e7d32'},
    ).add_to(value_layer)

    # ============================================================
    # TRANSPORT LINKS
    # ============================================================
    for stn in TUBE_STATIONS:
        is_elizabeth = "Elizabeth" in stn["lines"]
        stn_color = "#7B1FA2" if is_elizabeth else "#0D47A1"
        stn_icon = "train" if is_elizabeth or "National Rail" in stn["lines"] else "subway"

        popup_html = f"""
        <div style="width:250px;font-family:Arial,sans-serif;">
            <h4 style="margin:0 0 5px;color:{stn_color};">{stn['name']}</h4>
            <p style="margin:0 0 3px;"><b>Zone:</b> {stn['zone']}</p>
            <p style="margin:0;font-size:12px;">{stn['lines']}</p>
        </div>"""

        folium.Marker(
            location=stn["coords"],
            popup=folium.Popup(popup_html, max_width=270),
            tooltip=f"{stn['name']} (Zone {stn['zone']})",
            icon=folium.Icon(color="purple" if is_elizabeth else "darkblue", icon=stn_icon, prefix="fa"),
        ).add_to(transport_layer)

    # ============================================================
    # QUIET ZONES
    # ============================================================
    for area in QUIET_AREAS:
        popup_html = f"""
        <div style="width:260px;font-family:Arial,sans-serif;">
            <h4 style="margin:0 0 5px;color:#2e7d32;">&#10004; {area['name']}</h4>
            <p style="margin:0;font-size:13px;">{area['note']}</p>
        </div>"""
        folium.Marker(
            location=area["coords"],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"Quiet Zone: {area['name']}",
            icon=folium.Icon(color="green", icon="leaf", prefix="fa"),
        ).add_to(quiet_layer)

    # ============================================================
    # PROPERTY TIPS
    # ============================================================
    for tip in PROPERTY_TIPS:
        popup_html = f"""
        <div style="width:300px;font-family:Arial,sans-serif;">
            <h4 style="margin:0 0 8px;color:#1565c0;">{tip['name']}</h4>
            <p style="margin:0;font-size:13px;line-height:1.4;">{tip['tip']}</p>
        </div>"""
        folium.Marker(
            location=tip["coords"],
            popup=folium.Popup(popup_html, max_width=320),
            tooltip=tip["name"],
            icon=folium.Icon(color="blue", icon="info-circle", prefix="fa"),
        ).add_to(tips_layer)

    # ============================================================
    # Add layers
    # ============================================================
    for layer in [airports_layer, arrivals_layer, departures_layer, noise_layer,
                  live_layer, borough_layer, value_layer, transport_layer,
                  quiet_layer, tips_layer]:
        layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # ============================================================
    # GEOCODER (Address / Postcode Search)
    # ============================================================
    plugins.Geocoder(
        collapsed=True,
        position="topright",
        add_marker=True,
        placeholder="Search address or postcode...",
    ).add_to(m)

    # ============================================================
    # LEGEND
    # ============================================================
    legend_html = """
    <div id="legend-box" style="
        position:fixed; bottom:30px; left:10px;
        background:white; border:2px solid #666; border-radius:8px;
        padding:12px 16px; font-family:Arial,sans-serif; font-size:11px;
        z-index:9999; box-shadow:2px 2px 6px rgba(0,0,0,0.3); max-width:230px;
        max-height:400px; overflow-y:auto;
    ">
        <h4 style="margin:0 0 6px;font-size:13px;border-bottom:1px solid #ccc;padding-bottom:4px;">Legend</h4>
        <div style="margin-bottom:6px;">
            <b>Flight Paths</b><br>
            <span style="display:inline-block;width:18px;height:3px;background:#2196F3;vertical-align:middle;"></span> Arrival &nbsp;
            <span style="display:inline-block;width:18px;height:3px;background:#E91E63;vertical-align:middle;"></span> Departure<br>
            <span style="font-size:10px;color:#888;">Solid = High freq | Dashed = Medium</span>
        </div>
        <div style="margin-bottom:6px;border-top:1px solid #eee;padding-top:4px;">
            <b>Noise Zones</b><br>
            <span style="display:inline-block;width:10px;height:10px;background:#d32f2f;border-radius:50%;"></span> Severe (72+ dB)
            <span style="display:inline-block;width:10px;height:10px;background:#f57c00;border-radius:50%;"></span> High (63-72)<br>
            <span style="display:inline-block;width:10px;height:10px;background:#fdd835;border-radius:50%;"></span> Moderate (57-63)
            <span style="display:inline-block;width:10px;height:10px;background:#a5d6a7;border-radius:50%;"></span> Low (51-57)
        </div>
        <div style="margin-bottom:6px;border-top:1px solid #eee;padding-top:4px;">
            <b>Live Aircraft Altitude</b><br>
            <span style="display:inline-block;width:10px;height:10px;background:#d32f2f;border-radius:50%;"></span> &lt;3000ft (LOUD)
            <span style="display:inline-block;width:10px;height:10px;background:#f57c00;border-radius:50%;"></span> 3-6000ft<br>
            <span style="display:inline-block;width:10px;height:10px;background:#fdd835;border-radius:50%;"></span> 6-15000ft
            <span style="display:inline-block;width:10px;height:10px;background:#4caf50;border-radius:50%;"></span> 15000ft+
        </div>
        <div style="border-top:1px solid #eee;padding-top:4px;">
            <b>Value Score</b> (0-10)<br>
            <span style="font-size:10px;color:#555;">High = quiet + affordable + good growth</span><br>
            <span style="display:inline-block;width:10px;height:10px;background:#4caf50;border-radius:50%;"></span> 7+ Great
            <span style="display:inline-block;width:10px;height:10px;background:#f57c00;border-radius:50%;"></span> 5-7 OK
            <span style="display:inline-block;width:10px;height:10px;background:#d32f2f;border-radius:50%;"></span> &lt;5 Poor
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    # ============================================================
    # TITLE BAR
    # ============================================================
    flight_count = len([f for f in live_flights if not f["on_ground"]])
    title_html = f"""
    <div style="
        position:fixed; top:10px; left:50%; transform:translateX(-50%);
        background:rgba(26,35,126,0.92); color:white;
        padding:10px 24px; border-radius:8px;
        font-family:Arial,sans-serif; font-size:15px; font-weight:bold;
        z-index:9999; box-shadow:2px 2px 8px rgba(0,0,0,0.4); text-align:center;
        max-width:90%;
    ">
        London Flight Path & Property Buyer's Map v2.0
        <div style="font-size:11px;font-weight:normal;margin-top:3px;color:#bbdefb;">
            {flight_count} live aircraft | {len(BOROUGH_DATA)} boroughs with prices | {len(TUBE_STATIONS)} stations |
            Toggle layers on the right | Use search bar (top-right) for postcodes
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    # Plugins
    plugins.MiniMap(toggle_display=True).add_to(m)
    plugins.Fullscreen().add_to(m)
    plugins.MousePosition(position="bottomright").add_to(m)
    plugins.MeasureControl(position="topleft").add_to(m)

    return m


if __name__ == "__main__":
    print("=" * 60)
    print("London Flight Path & Property Map v2.0")
    print("=" * 60)
    m = create_map()
    output = "C:/Users/bilal/OneDrive/Desktop/London Flight Path Map/london_flight_paths.html"
    m.save(output)
    print(f"\nMap saved to: {output}")
    print("Open in your browser to explore!")
    print("\nFeatures:")
    print("  - Airports, flight paths, noise zones")
    print("  - Live aircraft positions (re-run to refresh)")
    print("  - Borough property prices + noise ratings")
    print("  - Value score heatmap (noise-adjusted)")
    print("  - Transport links (Tube, Elizabeth Line, Rail)")
    print("  - Postcode/address search bar")
    print("  - Quiet zone recommendations")
    print("  - Property buying tips")
