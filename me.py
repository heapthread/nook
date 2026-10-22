"""Answers about the visitor's own connection: `my ip`, `my user agent`.

Worked out from the request itself and shown back to the visitor. Nothing is stored."""
import re

import devtools

IP = {"my ip", "my ip address", "what is my ip", "what is my ip address", "what's my ip", "what's my ip address",
      "whats my ip", "whats my ip address", "show my ip", "ip address", "what is my public ip"}
AGENT = {"my user agent", "what is my user agent", "what's my user agent", "user agent", "my browser", "what browser am i using",
         "what is my browser"}


def answer(query, ip, user_agent):
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    if q in IP and ip:
        note = ("nook runs on your own computer, so this is its own address" if ip in ("127.0.0.1", "::1")
                else "the address nook sees you from; behind a proxy it can be the proxy's")
        return {"kind": "fact", "big": ip, "small": note}
    if q in AGENT and user_agent:
        return devtools.tool("your browser says", user_agent[:300])
    return None
