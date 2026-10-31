"""النشر على X عن طريق Buffer (بدل Typefully).
يحتاج secret في GitHub باسم BUFFER_API_KEY."""
import os
import re

import requests

KEY = os.environ.get("BUFFER_API_KEY", "")
ORG = "6ad4e416646572d047302037"
CHANNEL = "6ad4e485778b240e2f4a03a2"  # @fanFpl11
API = "https://api.buffer.com"


def _gql(query, variables=None):
    r = requests.post(API, headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
                                    "User-Agent": "fanFpl11-bot/1.0"},
                      json={"query": query, "variables": variables or {}}, timeout=60)
    try:
        return r.json()
    except ValueError:
        print("Buffer رد غريب:", r.status_code, r.text[:300], flush=True)
        raise


def _key(text):
    """أول سطرين من التغريدة بدون أرقام النتيجة (عشان نكشف التكرار)."""
    lines = [re.sub(r"\d+-\d+", "-", l.strip()) for l in text.splitlines() if l.strip() and "#" not in l]
    return re.sub(r"\s+", " ", " ".join(lines[:2]))[:40]


def already_posted(text, last=40):
    try:
        d = _gql("query($o:OrganizationId!,$n:Int){ posts(first:$n, input:{organizationId:$o}){ edges{ node{ text status } } } }",
                 {"o": ORG, "n": last})
        k = _key(text)
        for e in d["data"]["posts"]["edges"]:
            n = e["node"]
            if n["status"] in ("sent", "scheduled", "sending") and _key(n.get("text") or "") == k:
                print("مكررة، ما نشرتها:", k)
                return True
    except Exception as ex:
        print("تحقق التكرار فشل:", ex)
    return False


def post(text, image_urls=(), due_at=None, dedupe=True):
    """ينشر الحين، أو يجدول لو due_at (ISO) موجود. يرجع True لو نجح."""
    if dedupe and not due_at and already_posted(text):
        return True
    inp = {"channelId": CHANNEL, "text": text, "assets": [{"image": {"url": u}} for u in image_urls],
           "mode": "customScheduled" if due_at else "shareNow", "schedulingType": "automatic",
           "needsApproval": False}
    if due_at:
        inp["dueAt"] = due_at
    q = ("mutation($input: CreatePostInput!){ createPost(input:$input){ __typename "
         "... on PostActionSuccess { post { id status } } ... on MutationError { message } } }")
    try:
        d = _gql(q, {"input": inp})
        res = d.get("data", {}).get("createPost") or {}
        ok = res.get("__typename") == "PostActionSuccess"
        print("Buffer:", "تم" if ok else d, text.splitlines()[0])
        return ok
    except Exception as ex:
        print("Buffer فشل:", ex)
        return False
