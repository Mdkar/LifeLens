import streamlit as st
import openai
import os
from dotenv import load_dotenv
import uuid
import time
from openai.types.beta.threads.run import Run
import json
import requests
import googlemaps
from datetime import datetime

# Load the environment variables
load_dotenv()

# Set the API keys
GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_KEY")
IMMICH_API_KEY = os.getenv("IMMICH_API_KEY")
BASE_URL = os.getenv("IMMICH_URL")
openai.api_key = os.getenv("OPENAI_API_KEY")
client = openai.OpenAI()

# Your chosen model
MODEL = "gpt-3.5-turbo" 

# Google Maps API used only for better reverse geocoding of specific coordinates
gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

result_types = ["colloquial_area", "sublocality", "neighborhood", "premise", "subpremise", "natural_feature", "airport", "park", "point_of_interest"]

def get_specific_location(lat: str, lng: str) -> str:
    print("reverse geocoding " + lat + " " + lng)
    latlng = float(lat), float(lng)
    result = gmaps.reverse_geocode(latlng, result_type="|".join(result_types))
    out = set()
    for r in result:
        for ac in r['address_components']:
            # append if any of the types are in result_types
            if any([t in result_types for t in ac['types']]):
                out.add(ac['long_name'])
    out = list(out)
    return out

ignore_keys = {"thumbhash", "resized", "hasMetadata", "deviceAssetId", "ownerId", "deviceId", "libraryId", "originalPath", "originalFileName", "checksum", "faces"}

def trim_json(json: dict) -> dict:
    out = {k: v for k, v in json.items() if k not in ignore_keys}
    return out

def get_person_name(uuid: str) -> dict:
    print("getting person from id " + uuid)
    url = BASE_URL + f"/api/person/{uuid}"
    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }
    response = requests.request("GET", url, headers=headers)
    res = response.json()
    if "name" in res:
        return res["name"]
    return "Unknown"

def search_person(name: str) -> dict:
    print("searching for " + name)
    url = BASE_URL + "/api/search/person"
    payload = {'name': name}
    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }
    response = requests.request("GET", url, headers=headers, params=payload)
    rj = response.json()
    if len(rj) > 0:
        return rj[0]

def search_person_assets(name: str) -> list:
    person = search_person(name)
    url = BASE_URL + f"/api/person/{person['id']}/assets"
    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }
    response = requests.request("GET", url, headers=headers)
    rj = response.json()
    if len(rj) > 5:
        rj = rj[:5]
    return [trim_json(asset) for asset in rj]

def get_num_assets_from_id(uuid: str) -> int:
    print("getting num assets")
    url = BASE_URL + f"/api/person/{uuid}/statistics"
    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }
    response = requests.request("GET", url, headers=headers)
    return response.json()["assets"]

def get_num_assets(name: str) -> int:
    person = search_person(name)
    return get_num_assets_from_id(person["id"])

def asset_search(order: str = "desc", 
                 takenAfter: str = None, 
                 takenBefore: str = None, 
                 city: str = None, 
                #  state: str = None,
                #  country: str = None, 
                 num: str = "7") -> dict:
    num = int(num)
    payload = {'order': order, 'num': num, 'withPeople': "true", "withExif": "true"}
    if takenAfter:
        payload['takenAfter'] = takenAfter
    if takenBefore:
        payload['takenBefore'] = takenBefore
    if city:
        payload['city'] = city
    # if state:
    #     payload['state'] = state
    # if country:
    #     payload['country'] = country
    print("asset searching for asset " + str(payload))
    url = BASE_URL + "/api/assets/"
    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }
    response = requests.request("GET", url, headers=headers, params=payload)
    items = response.json()
    if "assets" in items and "items" in items["assets"]:
        items = items["assets"]["items"]
    if len(items) > num:
        items = items[:num]
    out = [trim_json(asset) for asset in items]
    return out

def smart_search(query: str, recent: str="false", num: str = "7") -> dict:
    print("smart searching for " + query + " " + recent + " " + num)
    num = int(num)
    url = BASE_URL + "/api/search/"
    payload = {'query': query, 'recent': recent, 'smart': "true"}
    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }
    response = requests.request("GET", url, headers=headers, params=payload)
    items = response.json()
    if "assets" in items and "items" in items["assets"]:
        items = items["assets"]["items"]
    if recent == "true":
        items.sort(key=lambda x: x["fileCreatedAt"], reverse=True)
    if len(items) > 10:
        items = items[:10]
    out = [trim_json(asset) for asset in items]
    return out

def get_birthday(name: str) -> str:
    person = search_person(name)
    bday = person["birthDate"]
    if bday:
        return bday
    return "unknown"

def get_thumbnail(id: str) -> bytes:
    print("getting thumbnail")
    url = BASE_URL + f"/api/asset/thumbnail/{id}"
    payload = {'format': 'JPEG'}
    headers = {
        'Accept': 'application/octet-stream',
        'x-api-key': IMMICH_API_KEY
    }
    response = requests.request("GET", url, headers=headers, params=payload)
    return response.content

def show_image(id: str):
    print("showing image" + id)
    st.session_state.thumbs.append(get_thumbnail(id))
    st.sidebar.image(st.session_state.thumbs)
    return "success"

def get_random_asset(number: str) -> tuple[list,list]:
    number = int(number)
    if type(number) != int:
        number = 1
    url = BASE_URL + "/api/asset/random"
    payload = {'count': number}
    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }
    response = requests.request("GET", url, headers=headers, params=payload)
    assets = response.json()
    thumbs = []
    for asset in assets:
        thumbs.append(get_thumbnail(asset['id']))
    assets = [trim_json(asset) for asset in assets]
    st.session_state.thumbs = thumbs
    st.sidebar.image(st.session_state.thumbs)
    return assets

def get_asset_details(id: str) -> dict:
    print("getting asset details "+ id)
    url = BASE_URL + f"/api/asset/{id}"
    headers = {
        'Accept': 'application/json',
        'x-api-key': IMMICH_API_KEY
    }
    response = requests.request("GET", url, headers=headers)
    return trim_json(response.json())

funcs = [get_birthday, 
         get_num_assets, 
         get_random_asset, 
         get_person_name, 
         get_asset_details, 
         get_specific_location, 
         search_person_assets, 
         show_image, 
         smart_search, 
         asset_search]

available_funcs = {f.__name__: f for f in funcs}


# Initialize session state variables
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "run" not in st.session_state:
    st.session_state.run = {"status": None}

if "messages" not in st.session_state:
    st.session_state.messages = []

if "retry_error" not in st.session_state:
    st.session_state.retry_error = 0

if "thumbs" not in st.session_state:
    st.session_state.thumbs = []

# Set up the page
st.set_page_config(page_title="LifeLens", page_icon=":camera:")
st.sidebar.title("LifeLens")
st.sidebar.divider()
st.sidebar.markdown("Mine your Immich photo library for context. Ask about your life.")
st.sidebar.divider()
st.sidebar.image(st.session_state.thumbs)

openai_tools_list = [
    {
        "type": "function",
        "function": {
            "name": "get_num_assets",
            "description": "Get the number of photos featuring a particular person",
            "parameters": {
                "type": "object",
                "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the person you are looking for"
                }
                },
                "required": [
                "name"
                ]
            }
        }
    }, {
        "type": "function",
        "function": {
            "name": "get_birthday",
            "description": "Get a person's birthday date",
            "parameters": {
                "type": "object",
                "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the person"
                }
                },
                "required": [
                "name"
                ]
            }
        }
    }, {
        "type": "function",
        "function": {
            "name": "get_random_asset",
            "description": "Get a list of asset objects representing random images from the library. The user is automatically shown these images.",
            "parameters": {
                "type": "object",
                "properties": {
                "number": {
                    "type": "string",
                    "description": "The number of images to return"
                }
                },
                "required": []
            }
        }
    }, {
        "type": "function",
        "function": {
            "name": "get_person_name",
            "description": "Get a person's name from their UUID",
            "parameters": {
                "type": "object",
                "properties": {
                "uuid": {
                    "type": "string",
                    "description": "The id of the person"
                }
                },
                "required": [
                "uuid"
                ]
            }
        }
    }, {
        "type": "function",
        "function": {
            "name": "get_asset_details",
            "description": "Get all the details of an image using it's asset id. Information returned may include UUIDs of people tagged in the image as well as some objects in the scene.",
            "parameters": {
                "type": "object",
                "properties": {
                "id": {
                    "type": "string",
                    "description": "The id of the asset"
                }
                },
                "required": [
                "id"
                ]
            }
        }
    }, {
        # Remove this if not using the Google Maps API
        "type": "function",
        "function": {
            "name": "get_specific_location",
            "description": "Get a list of location names for a given latitude and longitude",
            "parameters": {
                "type": "object",
                "properties": {
                "lat": {
                    "type": "string",
                    "description": "Latitude"
                },
                "lng": {
                    "type": "string",
                    "description": "Longitude"
                }
                },
                "required": [
                "lat",
                "lng"
                ]
            }
        }
    }, {
        "type": "function",
        "function": {
            "name": "search_person_assets",
            "description": "Get a list of asset objects representing images featuring a particular person. Only up to 5 of the latest images will be returned. You must use the asset ids returned to get more information about the photos.",
            "parameters": {
                "type": "object",
                "properties": {
                "name": {
                    "type": "string",
                    "description": "The name of the person"
                }
                },
                "required": [
                "name"
                ]
            }
        }
    }, {
        "type": "function",
        "function": {
            "name": "show_image",
            "description": "Show the image associated with the given asset id to the user",
            "parameters": {
                "type": "object",
                "properties": {
                "id": {
                    "type": "string",
                    "description": "The id of the asset"
                }
                },
                "required": [
                "id"
                ]
            }
        }
    }, {
        "type": "function",
        "function": {
            "name": "smart_search",
            "description": "Search for a list of asset objects representing images. The search is a similarity search comparing CLIP embeddings of the images to the query.",
            "parameters": {
                "type": "object",
                "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to search"
                },
                "recent": {
                    "type": "string",
                    "enum": [
                    "true",
                    "false"
                    ],
                    "description": "Whether to sort results by most recent"
                },
                "num": {
                    "type": "string",
                    "description": "number of results to return, defaults to 7"
                }
                },
                "required": [
                "query"
                ]
            }
        }
    }, {
        "type": "function",
        "function": {
            "name": "asset_search",
            "description": "Search for a list of asset objects representing images using only image metadata. Useful to find images taken at a particular time or city.",
            "parameters": {
                "type": "object",
                "properties": {
                "order": {
                    "type": "string",
                    "enum": [
                    "desc",
                    "asc"
                    ],
                    "description": "Ascending or descending (descending lists most recent first and is default)"
                },
                "takenBefore": {
                    "type": "string",
                    "description": "Datetime in YYYY-MM-DD format. Searches for images taken before this date."
                },
                "takenAfter": {
                    "type": "string",
                    "description": "Datetime in YYYY-MM-DD format. Searches for images taken after this date."
                },
                "city": {
                    "type": "string",
                    "description": "City to search for"
                },
                "num": {
                    "type": "string",
                    "description": "Maximum number of results to return, defaults to 7"
                }
                },
                "required": []
            }
        }
    }
]
# Initialize OpenAI assistant
if "assistant" not in st.session_state:
    assistant = client.beta.assistants.create(
        name = "Immich LifeLens",
        instructions = f"You can answer questions about a person's life based on information stored in their photos library. \
                        You can query relevant information from the photos library using the provided functions. \
                        Today is {datetime.today().strftime('%B %d, %Y')}. \
                        You must not reveal details about assets or images unless specifically prompted to.",
        tools = openai_tools_list,
        model = MODEL
    )
    # st.session_state.assistant = openai.beta.assistants.retrieve(os.getenv("OPENAI_ASSISTANT")) # if you want to use an existing assistant
    st.session_state.assistant = assistant
    st.session_state.thread = client.beta.threads.create(
        metadata={'session_id': st.session_state.session_id}
    )

elif hasattr(st.session_state.run, 'status') and st.session_state.run.status == "requires_action":
    run : Run = st.session_state.run
    ra = run.required_action
    if ra.type == 'submit_tool_outputs':
        calls = ra.submit_tool_outputs.tool_calls
        call_ids = []
        outputs = []
        for call in calls:
            if call.type == 'function':
                call_ids.append(call.id)
                f = available_funcs[call.function.name]
                output = f(**json.loads(call.function.arguments))
                outputs.append(output)
        run = client.beta.threads.runs.submit_tool_outputs(
            thread_id=st.session_state.thread.id,
            run_id=run.id,
            tool_outputs=[{"tool_call_id": call_ids[i], "output": json.dumps(outputs[i])} for i in range(len(call_ids))],
            )
        st.session_state.run = run

# Display chat messages
elif hasattr(st.session_state.run, 'status') and st.session_state.run.status == "completed":
    st.session_state.messages = client.beta.threads.messages.list(
        thread_id=st.session_state.thread.id
    )
    for message in reversed(st.session_state.messages.data):
        if message.role in ["user", "assistant"]:
            with st.chat_message(message.role):
                for content_part in message.content:
                    message_text = content_part.text.value
                    st.markdown(message_text)

# Chat input and message creation with file ID
if prompt := st.chat_input("How can I help you?"):
    with st.chat_message('user'):
        st.write(prompt)

    message_data = {
        "thread_id": st.session_state.thread.id,
        "role": "user",
        "content": prompt
    }

    # Include file ID in the request if available
    if "file_id" in st.session_state:
        message_data["file_ids"] = [st.session_state.file_id]

    st.session_state.messages = client.beta.threads.messages.create(**message_data)

    st.session_state.run = client.beta.threads.runs.create(
        thread_id=st.session_state.thread.id,
        assistant_id=st.session_state.assistant.id,
    )
    if st.session_state.retry_error < 3:
        time.sleep(1)
        st.rerun()

# Handle run status
if hasattr(st.session_state.run, 'status'):
    if st.session_state.run.status == "running":
        with st.chat_message('assistant'):
            st.write("Thinking ......")
        if st.session_state.retry_error < 3:
            time.sleep(1)
            st.rerun()

    elif st.session_state.run.status == "failed":
        st.session_state.retry_error += 1
        with st.chat_message('assistant'):
            if st.session_state.retry_error < 3:
                st.write("Run failed, retrying ......")
                time.sleep(3)
                st.rerun()
            else:
                st.error("FAILED: The OpenAI API is currently processing too many requests. Please try again later ......")

    elif st.session_state.run.status != "completed":
        st.session_state.run = client.beta.threads.runs.retrieve(
            thread_id=st.session_state.thread.id,
            run_id=st.session_state.run.id,
        )
        if st.session_state.retry_error < 3:
            time.sleep(3)
            st.rerun()