import json

import boto3

# Use us-east-1 where Amazon Nova models are available
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

BOROUGH_DATA = {
    # London boroughs (synced from frontend BOROUGH_DATA_RAW + BOROUGH_EXTRA)
    "Hounslow": {"noise":"severe","price":"£465K","growth":"3.2%","crime":"medium","crimeRate":89,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Piccadilly Line, South West Railway. Heathrow proximity."},
    "Hillingdon": {"noise":"severe","price":"£480K","growth":"2.8%","crime":"low","crimeRate":72,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Metropolitan and Piccadilly Lines, Elizabeth Line at West Drayton."},
    "Richmond upon Thames": {"noise":"high","price":"£825K","growth":"1.5%","crime":"low","crimeRate":58,"schools":"excellent","flood":"medium","airQuality":"good","transport":"good","transportNote":"District Line, South West Railway, Overground."},
    "Ealing": {"noise":"high","price":"£540K","growth":"4.1%","crime":"medium","crimeRate":88,"schools":"good","flood":"low","airQuality":"moderate","transport":"excellent","transportNote":"Elizabeth Line, Central, District, Piccadilly Lines."},
    "Wandsworth": {"noise":"moderate","price":"£680K","growth":"2.1%","crime":"medium","crimeRate":82,"schools":"excellent","flood":"medium","airQuality":"moderate","transport":"excellent","transportNote":"Northern Line, Overground, National Rail. Battersea extension."},
    "Lambeth": {"noise":"moderate","price":"£560K","growth":"3.5%","crime":"high","crimeRate":115,"schools":"good","flood":"medium","airQuality":"poor","transport":"excellent","transportNote":"Victoria, Northern, Bakerloo Lines. Waterloo and Vauxhall."},
    "Lewisham": {"noise":"low-moderate","price":"£445K","growth":"4.8%","crime":"medium","crimeRate":91,"schools":"good","flood":"medium","airQuality":"moderate","transport":"good","transportNote":"DLR, National Rail, Overground. Bakerloo extension planned."},
    "Greenwich": {"noise":"moderate","price":"£430K","growth":"5.2%","crime":"medium","crimeRate":93,"schools":"good","flood":"high","airQuality":"moderate","transport":"good","transportNote":"Elizabeth Line at Woolwich. DLR, Jubilee at North Greenwich."},
    "Tower Hamlets": {"noise":"low-moderate","price":"£495K","growth":"2.0%","crime":"high","crimeRate":120,"schools":"good","flood":"high","airQuality":"poor","transport":"excellent","transportNote":"DLR, Central, District, Jubilee, Elizabeth Lines."},
    "Camden": {"noise":"low","price":"£780K","growth":"1.2%","crime":"high","crimeRate":130,"schools":"excellent","flood":"low","airQuality":"poor","transport":"excellent","transportNote":"Northern, Victoria, Metropolitan, Piccadilly. King's Cross, Euston."},
    "Islington": {"noise":"low","price":"£720K","growth":"1.8%","crime":"high","crimeRate":125,"schools":"good","flood":"low","airQuality":"poor","transport":"excellent","transportNote":"Victoria, Northern, Piccadilly Lines. King's Cross nearby."},
    "Hackney": {"noise":"low","price":"£590K","growth":"3.0%","crime":"high","crimeRate":112,"schools":"good","flood":"low","airQuality":"moderate","transport":"excellent","transportNote":"Overground, National Rail. Best cycling infrastructure."},
    "Barnet": {"noise":"low-moderate","price":"£560K","growth":"3.1%","crime":"low","crimeRate":74,"schools":"excellent","flood":"low","airQuality":"good","transport":"good","transportNote":"Northern Line (High Barnet/Edgware). Thameslink."},
    "Croydon": {"noise":"moderate","price":"£395K","growth":"4.5%","crime":"medium","crimeRate":98,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"East Croydon major rail hub. Tramlink network."},
    "Bromley": {"noise":"low","price":"£480K","growth":"3.8%","crime":"low","crimeRate":65,"schools":"excellent","flood":"low","airQuality":"good","transport":"moderate","transportNote":"National Rail to London Bridge/Victoria. No tube."},
    "Newham": {"noise":"moderate-high","price":"£410K","growth":"5.8%","crime":"high","crimeRate":108,"schools":"good","flood":"high","airQuality":"poor","transport":"excellent","transportNote":"Elizabeth Line, Jubilee, DLR, Central. Stratford interchange."},
    "Southwark": {"noise":"low-moderate","price":"£530K","growth":"2.5%","crime":"high","crimeRate":118,"schools":"good","flood":"medium","airQuality":"poor","transport":"excellent","transportNote":"Jubilee, Northern, Bakerloo. London Bridge hub."},
    "Hammersmith and Fulham": {"noise":"moderate-high","price":"£750K","growth":"1.0%","crime":"medium","crimeRate":96,"schools":"excellent","flood":"high","airQuality":"moderate","transport":"excellent","transportNote":"District, Piccadilly, Central Lines. Hammersmith interchange."},
    "Kensington and Chelsea": {"noise":"moderate","price":"£1,350K","growth":"0.5%","crime":"medium","crimeRate":95,"schools":"excellent","flood":"medium","airQuality":"moderate","transport":"excellent","transportNote":"District, Circle, Central, Piccadilly Lines."},
    "Brent": {"noise":"low-moderate","price":"£490K","growth":"4.0%","crime":"medium","crimeRate":92,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Jubilee, Bakerloo, Metropolitan Lines. Wembley Park."},
    "Haringey": {"noise":"low","price":"£545K","growth":"3.5%","crime":"medium","crimeRate":99,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Victoria, Piccadilly Lines, Overground."},
    "Waltham Forest": {"noise":"low","price":"£480K","growth":"4.2%","crime":"medium","crimeRate":88,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Victoria Line, Central Line, Overground."},
    "Merton": {"noise":"low-moderate","price":"£560K","growth":"2.8%","crime":"low","crimeRate":70,"schools":"good","flood":"low","airQuality":"moderate","transport":"good","transportNote":"District, Northern Lines. Tramlink. Wimbledon interchange."},
    "Redbridge": {"noise":"low","price":"£445K","growth":"3.9%","crime":"medium","crimeRate":83,"schools":"excellent","flood":"low","airQuality":"moderate","transport":"good","transportNote":"Central Line, Elizabeth Line at Ilford."},
    "Enfield": {"noise":"low","price":"£430K","growth":"4.3%","crime":"medium","crimeRate":85,"schools":"good","flood":"low","airQuality":"good","transport":"moderate","transportNote":"Piccadilly Line, Overground, National Rail."},
    "Kingston upon Thames": {"noise":"low-moderate","price":"£550K","growth":"2.0%","crime":"low","crimeRate":62,"schools":"excellent","flood":"medium","airQuality":"good","transport":"good","transportNote":"South West Railway to Waterloo. No tube."},
    "Sutton": {"noise":"low","price":"£415K","growth":"3.5%","crime":"low","crimeRate":60,"schools":"excellent","flood":"low","airQuality":"good","transport":"moderate","transportNote":"National Rail to London Bridge/Victoria. Tramlink."},
    "Westminster": {"noise":"moderate","price":"£980K","growth":"0.8%","crime":"high","crimeRate":175,"schools":"good","flood":"medium","airQuality":"poor","transport":"excellent","transportNote":"Every tube line nearby. Victoria, Waterloo, Paddington."},
    "City of London": {"noise":"low-moderate","price":"£850K","growth":"1.0%","crime":"high","crimeRate":190,"schools":"good","flood":"medium","airQuality":"poor","transport":"excellent","transportNote":"Central, Circle, District, Metropolitan, Northern, Elizabeth Lines."},
    "Barking": {"noise":"low","price":"£340K","growth":"5.8%","crime":"high","crimeRate":105,"schools":"good","flood":"medium","airQuality":"moderate","transport":"good","transportNote":"District Line, Hammersmith & City, c2c. Barking hub."},
    "Havering": {"noise":"low","price":"£400K","growth":"4.0%","crime":"low","crimeRate":72,"schools":"good","flood":"low","airQuality":"good","transport":"moderate","transportNote":"Elizabeth Line at Romford. District Line at Upminster."},
    "Bexley": {"noise":"low","price":"£380K","growth":"4.5%","crime":"low","crimeRate":68,"schools":"good","flood":"medium","airQuality":"good","transport":"moderate","transportNote":"Elizabeth Line at Abbey Wood. National Rail."},
    "Harrow": {"noise":"low","price":"£490K","growth":"3.2%","crime":"low","crimeRate":70,"schools":"excellent","flood":"low","airQuality":"good","transport":"good","transportNote":"Metropolitan Line. Bakerloo to Harrow & Wealdstone."},
    # NYC boroughs (synced from frontend NYC_BOROUGH_DATA_RAW + NYC_BOROUGH_EXTRA)
    "Queens": {"noise":"severe","price":"$620K","growth":"4.5%","crime":"medium","crimeRate":78,"schools":"good","flood":"high","airQuality":"moderate","transport":"excellent","transportNote":"7 train, E/F/M/R, LIRR, JFK AirTrain."},
    "Brooklyn": {"noise":"high","price":"$850K","growth":"3.8%","crime":"medium","crimeRate":82,"schools":"good","flood":"medium","airQuality":"moderate","transport":"excellent","transportNote":"Multiple subway lines, LIRR Atlantic Terminal."},
    "Manhattan": {"noise":"moderate","price":"$1,200K","growth":"2.0%","crime":"medium","crimeRate":95,"schools":"excellent","flood":"medium","airQuality":"poor","transport":"excellent","transportNote":"Every subway line. PATH to NJ. Metro-North."},
    "Bronx": {"noise":"low-moderate","price":"$420K","growth":"5.5%","crime":"high","crimeRate":110,"schools":"good","flood":"low","airQuality":"poor","transport":"good","transportNote":"4/5/6, B/D, Metro-North."},
    "Staten Island": {"noise":"low","price":"$550K","growth":"3.0%","crime":"low","crimeRate":52,"schools":"good","flood":"high","airQuality":"good","transport":"poor","transportNote":"Staten Island Railway, free ferry. Car-dependent."}
}

SYSTEM_PROMPT = f"""You are an AI property advisor for London and New York City. You help property buyers assess areas based on real data.

You have access to data for 34 London boroughs and 5 NYC boroughs covering: noise impact, average property prices, price growth, crime rates, school ratings, flood risk, air quality, and transport links.

Borough data:
{json.dumps(BOROUGH_DATA, indent=2)}

Guidelines:
- Be specific: quote actual prices, crime rates, transport lines
- Be honest about trade-offs (e.g. "quieter but longer commute")
- CRITICAL: Your noise assessment MUST match the borough data. If a borough has noise "severe" or "high", never describe it as quiet, peaceful, or having "quiet skies". If noise is "low", you can highlight the quiet environment. Never contradict the noise level.
- When asked to recommend areas, suggest 2-3 options with reasoning
- Mention the Buyer Value Score factors: Quiet Skies (40%), Affordability (35%), Growth (25%)
- Always remind users this is guidance, not professional property advice
- Keep responses concise (2-3 paragraphs max)
- If asked about a specific postcode, relate it to the nearest borough data
"""


INSIGHT_PROMPT = """Based on the following property data for a specific location, write a concise 2-3 sentence buyer insight. Be direct and honest about trade-offs. Do not use bullet points. Do not repeat the data - interpret it and give actionable advice.

CRITICAL: Your assessment of noise MUST match the noise data below. If noise is High (score 7+), you MUST mention significant aircraft noise as a key concern - never describe the area as quiet or peaceful. If noise is Low (score 0-3), you can highlight the quiet environment. Be consistent - do not contradict the noise level in any part of your response.

City: {city}
Location: {location}
Borough: {borough}
Noise level: {noise} (score {noise_score}/10 where 10 is noisiest)
Buyer Value Score: {score}/10
Nearest airport: {airport} ({airport_dist} km)
Nearest flight path: {path_dist} km away
Crime: {crime}
Schools: {schools}

Write the insight as if speaking directly to a buyer considering this area."""


COMPLEX_KEYWORDS = [
    'compare', 'recommend', 'best', 'worst', 'rank', 'investment',
    'which borough', 'where should', 'top 5', 'top 3', 'top 10',
    'negotiate', 'vs', 'versus', 'better than', 'safer than',
    'family with', 'commute to', 'budget of', 'under 400', 'under 500',
    'under 600', 'under 700', '5 year', 'five year', 'long term',
    'first time buyer', 'rental yield', 'regeneration',
]


def is_complex_query(message):
    msg_lower = message.lower()
    matches = sum(1 for kw in COMPLEX_KEYWORDS if kw in msg_lower)
    return matches >= 1 and len(message) > 30


def handler(event, context):
    try:
        body = json.loads(event.get('body', '{}'))
        mode = body.get('mode', 'chat')

        # Mode 1: Auto-insight for a searched location
        if mode == 'insight':
            location_data = body.get('locationData', {})
            prompt = INSIGHT_PROMPT.format(**location_data)
            reply = call_nova(
                [{'role': 'user', 'content': [{'text': prompt}]}],
                max_tokens=256
            )
            return response(200, {'reply': reply})

        # Mode 2: Multi-turn chat with conversation history
        message = body.get('message', '')
        history = body.get('history', [])
        viewing_context = body.get('context', '')

        if not message:
            return response(400, {'error': 'Message is required'})

        # Build conversation messages from history
        messages = []
        for msg in history[-8:]:  # Keep last 8 messages for context window
            messages.append({
                'role': msg['role'],
                'content': [{'text': msg['text']}]
            })

        # Add context about what user is viewing
        user_text = message
        if viewing_context:
            user_text = f"[User is currently viewing: {viewing_context}]\n\n{message}"

        messages.append({'role': 'user', 'content': [{'text': user_text}]})

        # Route complex queries to Nova Pro for deeper reasoning
        if is_complex_query(message):
            reply = call_nova_pro(messages, max_tokens=1536)
        else:
            reply = call_nova(messages, max_tokens=1024)
        return response(200, {'reply': reply, 'model': 'pro' if is_complex_query(message) else 'lite'})

    except Exception as e:
        return response(500, {'error': str(e)})


def call_nova(messages, max_tokens=1024):
    result = bedrock.invoke_model(
        modelId='us.amazon.nova-2-lite-v1:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            'messages': messages,
            'system': [{'text': SYSTEM_PROMPT}],
            'inferenceConfig': {
                'maxTokens': max_tokens,
                'temperature': 0.7,
                'topP': 0.9
            }
        })
    )
    result_body = json.loads(result['body'].read())
    return result_body['output']['message']['content'][0]['text']


def call_nova_pro(messages, max_tokens=1536):
    """Use Nova Pro for complex multi-criteria queries requiring deeper reasoning."""
    result = bedrock.invoke_model(
        modelId='us.amazon.nova-pro-v1:0',
        contentType='application/json',
        accept='application/json',
        body=json.dumps({
            'messages': messages,
            'system': [{'text': SYSTEM_PROMPT}],
            'inferenceConfig': {
                'maxTokens': max_tokens,
                'temperature': 0.7,
                'topP': 0.9
            }
        })
    )
    result_body = json.loads(result['body'].read())
    return result_body['output']['message']['content'][0]['text']


def response(status, body):
    return {
        'statusCode': status,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(body)
    }
