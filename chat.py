from gpt_session import Session
from uuid import uuid4
import time,json
from curl_cffi import Response

class ChatTransportError(RuntimeError):
    """Raised when the ChatGPT transport cannot complete a request."""

    def __init__(
        self,
        status_code=None,
        url=None,
        cf_mitigated=None,
        body_preview="",
    ):
        self.status_code = status_code
        self.url = url
        self.cf_mitigated = cf_mitigated
        self.body_preview = body_preview

        parts = ["Chat transport failed"]

        if status_code is not None:
            parts.append(f"HTTP {status_code}")

        if cf_mitigated:
            parts.append(f"cf-mitigated={cf_mitigated}")

        if url:
            parts.append(str(url))

        super().__init__(": ".join(parts))


class ChatGPT(Session):
    
    def __init__(self,**kwargs):
        self.message_handler = None
        #self.device_id = kwargs.get('device_id',None)
        self.message = kwargs.get('message',None)
        self.message_id = kwargs.get('message_id',None)
        self.conversation_id = kwargs.get('conversation_id', None)
        self.parent_message_id = kwargs.get('parent_message_id', "client-created-root")
        super().__init__()
    
    def query_gpt(self):
        self.session.get()
    
    def get_chat_payload(self,text):
        
        #models = [ "auto", "gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-4-gizmo"]
        json_data = {
    
            "action": "next",
            "messages": [
                {
                    "id": str(uuid4()),
                    "author": { "role": "user" },
                    "create_time": time.time(),
                    "content": { "content_type": "text", "parts": [text] },
                    "metadata": { "selected_github_repos": [], "selected_all_github_repos": False, "serialization_metadata": { "custom_symbol_offsets": [] } }
                }
            ],
            "parent_message_id": self.parent_message_id,
            "model": "auto",
            "timezone_offset_min": -60,
            "timezone": "Africa/Lagos",
            "conversation_mode": { "kind": "primary_assistant" },
            "enable_message_followups": True,
            "system_hints": [],
            "supports_buffering": True,
            "supported_encodings": ["v1"],
            "client_contextual_info": { "is_dark_mode": True, "time_since_loaded": 8, "page_height": 883, "page_width": 498, "pixel_ratio": 1.0909090909090908, "screen_height": 990, "screen_width": 1760 },
            "paragen_cot_summary_display_override": "allow"
        }
        
        if self.conversation_id:
            json_data["conversation_id"] = self.conversation_id
            
        return json_data
    
    def get_cookies():
        return {}
    
    def get_headers(self):
        return {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Accept': 'text/event-stream',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://chatgpt.com/',
        'OAI-Language': 'en-US',
        'OAI-Device-Id': self.device_id,
        'OAI-Client-Version': self.build_number,
        'Content-Type': 'application/json',
        'OpenAI-Sentinel-Chat-Requirements-Token': self.sentinel.get("token"),
        'OpenAI-Sentinel-Turnstile-Token': self.sentinel.get("turnstile"),
        'OpenAI-Sentinel-Proof-Token': self.sentinel.get("proof"),
        'Origin': 'https://chatgpt.com',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Priority': 'u=0',
    }
        

    def safe_parse(self,data_str):
        data = json.loads(data_str)
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                pass
        return data

    def decode_stream(self, response: Response):
        buffer = ""

        for chunk in response.iter_content(chunk_size=1024):
            if not chunk:
                continue

            buffer += chunk.decode("utf-8")
            lines = buffer.split("\n")
            buffer = lines.pop()

            for line in lines:
                if line.startswith("data:"):
                    data_str = line[len("data:"):].strip()

                    if data_str == "[DONE]":
                        return

                    try:
                        data = self.safe_parse(data_str)
                    except json.JSONDecodeError:
                        continue

                    if isinstance(data, dict):
                        if "conversation_id" in data:
                            self.conversation_id = data["conversation_id"]
                        
                        if data.get("type") == "message_marker" and "message_id" in data:
                            self.parent_message_id = data["message_id"]
                        
                        # Fallback for parent_message_id from message object
                        v = data.get("v")
                        if isinstance(v, dict) and "message" in v:
                            msg = v["message"]
                            if msg.get("author", {}).get("role") == "assistant":
                                self.parent_message_id = msg.get("id")

                    # Skip known metadata
                    if (
                        not isinstance(data, dict)
                        or "finish_details" in data
                        or data.get("type") == "message_stream_complete"
                    ):
                        continue

                    v = data.get("v")
                    if v is None:
                        continue

                    if isinstance(v, list):
                        for patch in v:
                            if isinstance(patch, dict) and patch.get("o") == "append":
                                val = patch.get("v")
                                if not isinstance(val, dict):
                                    yield val
                               

                    elif isinstance(v, str):
                        #print("finish_details v", "finish_details" in v)
                        yield v


    
    def reply_chat(self,text):
        
        self.get_requirements()
        json_data = self.get_chat_payload(text)
        headers = self.get_headers()
        
        response = self.session.post('https://chatgpt.com/backend-anon/conversation', headers=headers, json=json_data,stream=True,impersonate="chrome")
        
        if not response.ok:
            try:
                body_preview = response.text[:1000]
            except Exception:
                body_preview = ""

            raise ChatTransportError(
                status_code=response.status_code,
                url=str(getattr(response, "url", "")),
                cf_mitigated=response.headers.get("cf-mitigated"),
                body_preview=body_preview,
            )

        for chunk in self.decode_stream(response):
            # print(chunk, end="", flush=True)
            yield chunk
        
       

#uvicorn app:app --host 0.0.0.0 --port 5000
