import os
import re
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import torch
import uvicorn
from chromadb import PersistentClient
from dotenv import load_dotenv
from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from transformers import pipeline

print("Loading Embedding Model...")
embedding_model = SentenceTransformer(
    "BAAI/bge-base-en-v1.5"
)

load_dotenv()

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

print("Connecting to ChromaDB...")

if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI is not set. Add it to your .env file:\n"
        "MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/dbname"
    )

# ----------------------------------------------------------------------------
# Auth helper
# ----------------------------------------------------------------------------

def clean_auth_token(auth_token: str) -> str:
    if not auth_token:
        return auth_token
    token = auth_token.strip()
    lower = token.lower()
    if lower.count("bearer") > 1:
        return "Bearer " + token.split(" ")[-1]
    if not lower.startswith("bearer "):
        return "Bearer " + token
    return token

while True:

class SessionStore:
    def __init__(self, mongo_db):
        self._collection = mongo_db["chat_sessions"]
        self._cache: dict[str, dict] = {}

    async def ensure_indexes(self):
        try:
            await self._collection.create_index("session_id", unique=True)
            await self._collection.create_index(
                "updated_at",
                expireAfterSeconds=SESSION_TTL_SECONDS,
            )
        except Exception as e:
            log.warning(f"Could not create session indexes: {e}")

    async def get(self, session_id: str) -> dict:
        if session_id in self._cache:
            return self._cache[session_id]
        doc = await self._collection.find_one({"session_id": session_id})
        if doc is None:
            session = {**DEFAULT_SESSION, "wishlist": [], "session_id": session_id}
        else:
            session = {
                "wishlist": doc.get("wishlist", []),
                "pending_item": doc.get("pending_item"),
                "pending_intent": doc.get("pending_intent"),
                "session_id": session_id,
            }
        self._cache[session_id] = session
        return session

    async def save(self, session_id: str, session: dict):
        self._cache[session_id] = session
        try:
            await self._collection.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "wishlist": session.get("wishlist", []),
                        "pending_item": session.get("pending_item"),
                        "pending_intent": session.get("pending_intent"),
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
        except Exception as e:
            log.warning(f"Failed to persist session {session_id}: {e}")

# ----------------------------------------------------------------------------
# Intent keywords / lexicons
# ----------------------------------------------------------------------------

INTENT_KEYWORDS = {
    "view_cart":      ["view cart", "show cart", "my cart", "what's in my cart", "cart items", "see cart"],
    "wishlist_remove":["remove from wishlist", "delete from wishlist", "remove wishlist", "clear wishlist", "empty wishlist"],
    "wishlist":       ["show wishlist", "view wishlist", "my wishlist", "save for later", "add to wishlist"],
    "status":         ["order status", "track my order", "where is my order", "track order"],
    "cancel":         ["cancel my order", "cancel order", "stop my order"],
    "browse":         ["what do you have", "available items", "list all products", "show catalogue", "show me all"],
    "delete_cart":    ["remove from cart", "delete from cart", "remove item", "delete item", "take out", "remove my", "delete my"],
    "checkout":       ["place my order", "confirm order", "checkout", "place order", "proceed to payment"],
    # FIX: added "show me", "is there", "do you have", "in stock", "stock of", "cost of" back
    "product_info":   ["find", "search for", "look for", "is available", "available today",
                       "price of", "how much is", "how much does", "tell me about", "details of",
                       "what is the price", "show me", "is there", "do you have",
                       "in stock", "stock of", "cost of"],
    "order":          ["order my wishlist", "buy", "add to cart", "get me", "i want", "i need", "want to buy"],
}

CLOSING_WORDS = {"thank you", "thanks", "thx", "thank u", "appreciate it"}

CATEGORY_SYNONYMS = {
    "fruit":     ["fruit", "fruits"],
    "vegetable": ["vegetable", "vegetables", "veg"],
    "leafy":     ["leafy", "spinach", "methi", "palak", "coriander", "greens"],
}

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "half": 0.5, "dozen": 12, "a": 1, "an": 1,
}

UNIT_NORMALISE = {
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilogram": "kg",
    "g": "g", "gm": "g", "gram": "g",
    "l": "litre", "ltr": "litre", "liter": "litre",
    "ml": "ml",
    "dozen": "dozen",
    "piece": "piece", "pc": "piece",
    "packet": "packet", "pack": "packet",
    "bunch": "bunch", "box": "box",
}

STOP_WORDS = {
    "order", "food", "delivery", "item", "please", "want", "need", "get", "buy",
    "some", "and", "the", "of", "from", "in", "all", "available", "show", "list",
    "under", "below", "rs", "rupees", "today", "now", "any", "for", "about",
    "price", "cost", "what", "is", "are", "do", "you", "have", "there", "how", "much",
    "into", "my", "cart", "to", "onto", "me","fresh","organic"
}

UNIT_WORDS_RE = r"(kilograms?|kilos?|kg|grams?|gms?|g|litres?|liters?|ltr|mls?|ml|dozen|pieces?|pcs?|packets?|bunches?|boxes?|box)\b"
NUM_WORDS_RE  = r"(\d+\.?\d*|\b(?:half|one|two|three|four|five|six|seven|eight|nine|ten|dozen|a|an)\b)"

TYPO_MAP = {
    "ttoday": "today", "todday": "today", "todat": "today",
    "avaliable": "available", "availble": "available", "availabel": "available",
    "prise": "price", "prce": "price",
    "hwo": "how", "whats": "what is",
}

PRODUCT_QUERY_PHRASES = [
    "what is the price of", "price of", "how much is", "tell me about",
    "details of", "do you have", "is there", "show me", "find", "search for", "look for",
]
PRODUCT_FILLER_WORDS = {
    "today", "available", "please", "the", "a", "an", "is", "are", "any", "some",
    "about", "for", "now", "details", "me", "show", "all", "under", "below", "less",
    "than", "at", "most", "maximum", "max", "within", "rs", "rupees", "what", "much",
    "price", "cost", "do", "you", "have", "there", "how", "find", "search", "look",
}

# FIX: added extract_item_name — was missing, caused NameError on "delete apple"
CART_REMOVE_PHRASES = [
    "remove from cart", "delete from cart", "remove item", "delete item",
    "take out", "remove my", "delete my", "don't want", "dont want",
    "remove", "delete", "drop",
]

def extract_item_name(query: str) -> str | None:
    q = query.lower()
    for phrase in CART_REMOVE_PHRASES:
        q = q.replace(phrase, "")
    words = [w for w in q.split() if w not in STOP_WORDS and len(w) >= 2]
    return " ".join(words).strip().title() if words else None

# ----------------------------------------------------------------------------
# Text normalisation / intent detection
# ----------------------------------------------------------------------------

def normalize_query(q: str) -> str:
    for typo, fix in TYPO_MAP.items():
        q = q.replace(typo, fix)
    return q

def looks_like_price_filter(q: str) -> bool:
    return bool(re.search(r"\b(under|below|less than|at most|maximum|max|within)\b", q))

def looks_like_category_browse(q: str) -> bool:
    return bool(re.search(r"\b(fruits?|vegetables?|veg|leafy|greens?|beverages?|drinks?|juice)\b", q))

def detect_intent(query: str) -> tuple[str, float]:
    q = normalize_query(query.lower().strip())

    if q in {"hi", "hello", "hey", "namaste", "good morning", "good evening", "good afternoon"}:
        return "greeting", 1.0
    if q in CLOSING_WORDS:
        return "courtesy", 1.0
    if looks_like_category_browse(q) or looks_like_price_filter(q):
        return "browse", 1.0

    action_verb_start = bool(re.match(r"^(add|remove|delete|buy|order|get|put)\s+", q))

    priority_order = [
        "view_cart", "wishlist_remove", "wishlist", "status", "cancel",
        "browse", "delete_cart", "checkout", "product_info", "order",
    ]

    for intent in priority_order:
        if intent == "view_cart" and action_verb_start:
            continue
        if any(kw in q for kw in INTENT_KEYWORDS.get(intent, [])):
            return intent, 1.0

    if re.search(r"\b(what do you mean by|tell me about|explain|what does .* mean|meaning of)\b", q):
        return "rag", 1.0
    if re.match(r"^(what|who|why|how)\b", q) and "cart" not in q and "wishlist" not in q and "order" not in q:
        return "rag", 1.0
    if re.search(r"\b(remove|delete|take out|drop)\b.*\bcart\b", q):
        return "delete_cart", 1.0
    if re.match(r"^(add|order|buy|get)\s+", q):
        return "order", 1.0
    if re.search(r"\b(available|in stock|price|cost|how much|do you have|is there)\b", q):
        return "product_info", 0.6
    if re.search(rf"\b{NUM_WORDS_RE}\b.*{UNIT_WORDS_RE}", q):
        return "order", 0.6
    if re.search(r"\b(how (can|do|to) i (order|buy|get)|want to order|how to order)\b", q):
        return "order", 1.0
    return "rag", 0.3

INTENT_LABELS = [
    "greeting", "courtesy", "view_cart", "wishlist", "wishlist_remove",
    "status", "cancel", "browse", "delete_cart", "checkout",
    "product_info", "order", "rag",
]

async def llm_intent_fallback(query: str, pipe) -> str | None:
    if pipe is None:
        return None
    try:
        prompt = (
            "Classify the user's shopping-assistant message into exactly one label "
            f"from this list: {', '.join(INTENT_LABELS)}.\n"
            "Reply with ONLY the label, nothing else.\n\n"
            f"Message: \"{query}\"\nLabel:"
        )
        messages = [{"role": "user", "content": prompt}]
        loop = asyncio.get_running_loop()

        query_embedding = embedding_model.encode(
            query
        ).tolist()

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5
        )

        docs = results["documents"][0]

        scores = reranker.compute_score(
            [[query, doc] for doc in docs]
        )
        service_status["qwen_pipeline"] = True
        log.info("Local LLM loaded.")
    except Exception as e:
        log.error(f"Failed to load Qwen ({QWEN_MODEL_NAME}): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, db, session_store, http_client

        top_chunks = [
            doc[:500]
            for doc, score in ranked_docs[:2]
        ]

    loop = asyncio.get_running_loop()
    await asyncio.gather(
        loop.run_in_executor(None, load_embedding_model),
        loop.run_in_executor(None, load_reranker),
        loop.run_in_executor(None, load_chroma_collection),
        loop.run_in_executor(None, load_qwen_pipeline),
    )

        print("\n===== RETRIEVED CONTEXT =====\n")
        print(context[:1000])
        print("\n=============================\n")
        prompt = f"""
You are a documentation-based assistant.

RULES:
- Answer ONLY using the provided context.
- Do NOT use external knowledge.
- If the answer is not in the context, reply exactly:
  "Not found in documentation."
- Do not guess or add information that is not present.
- Keep the answer short and precise.

CONTEXT:
{context}

QUESTION:
{query}

ANSWER:
"""

        response = generator(
    prompt,
    max_new_tokens=40,
    do_sample=False,
    temperature=None,
    top_p=None,
    top_k=None,
    return_full_text=False,
    eos_token_id=generator.tokenizer.eos_token_id
)

@app.get("/health")
async def health():
    return {"status": "ok", "services": service_status}

        print("\nAssistant:")
        print(final_answer)

    query_words = set(w for w in re.findall(r"[a-z]+", clean_name) if len(w) >= 3)

    def is_relevant(candidate_name: str) -> bool:
        if not candidate_name:
            return False
        cand = candidate_name.lower()
        if clean_name in cand or cand in clean_name:
            return True
        cand_words = set(w for w in re.findall(r"[a-z]+", cand) if len(w) >= 3)
        if not query_words or not cand_words:
            return False
        return len(query_words & cand_words) > 0

    headers      = {"Authorization": auth_token}
    search_terms = [
        clean_name,
        clean_name[:-1] if clean_name.endswith("s") else clean_name + "s",
    ]

    for term in search_terms:
        try:
            response = await http_client.get(
                f"{NESTJS_BACKEND_URL}/customer/products",
                params={"search": term},
                headers=headers,
            )
            if response.status_code == 200:
                data     = response.json()
                products = data if isinstance(data, list) else (
                    data.get("data") or data.get("products") or data.get("items") or []
                )
                for prod in products:
                    name = prod.get("name", "")
                    if is_relevant(name):
                        return prod.get("_id") or prod.get("id"), name or clean_name
        except Exception as e:
            log.warning(f"find_product_id failed for '{term}': {e}")

    return None, None

async def fetch_store_name_cache(store_id: str, auth_token: str, cache: dict) -> str:
    return "Sahachari"

def extract_product_name(item: dict) -> str:
    for key in ("product", "productId"):
        nested = item.get(key)
        if isinstance(nested, dict):
            for field in ("name", "title", "itemName"):
                if nested.get(field):
                    return nested[field]
    for field in ("name", "productName", "title"):
        if item.get(field):
            return item[field]
    return "Unknown Item"

async def fetch_nestjs_cart_summary(auth_token: str) -> str:
    if not auth_token:
        return "⚠️ Error: Authorization token missing. Please log into Sahachari."
    token = clean_auth_token(auth_token)
    try:
        response = await http_client.get(
            f"{NESTJS_BACKEND_URL}/customer/cart",
            headers={"Authorization": token},
        )
        if response.status_code == 200:
            cart_data = response.json()
            items = cart_data.get("items", [])
            if not items:
                return "🛒 Your Sahachari cart is currently empty."
            
            lines = [f"🛒 Your Cart ({len(items)} items)", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
            grand_total = 0.0

            for idx, item in enumerate(items, 1):
                name = extract_product_name(item)
                qty = item.get("quantity", 1)
                
                # Extract pricing safely from either a nested product object or the item root
                product_data = item.get("product", {}) if isinstance(item.get("product"), dict) else item
                
                # Check for common price fields returned by NestJS
                price_field = product_data.get("finalPrice") or product_data.get("price") or 0.0
                try:
                    price = float(price_field)
                except (ValueError, TypeError):
                    price = 0.0
                
                item_total = price * qty
                grand_total += item_total
                
                # Dynamically inject the calculated subtotal into your layout
                lines.append(f"  {idx}. {name:<14} x{qty:<3} (₹{item_total:.2f})")
            
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            # Dynamically inject the computed grand total
            lines.append(f"💰 Total Amount: ₹{grand_total:.2f}")
            return "\n".join(lines)
            
    except Exception as e:
        log.warning(f"fetch_nestjs_cart_summary failed: {e}")
    return "🛒 Instantly saved to database. View your Cart UI panel!"
async def forward_to_nestjs_cart(items: list, auth_token: str) -> str:
    if not auth_token:
        return "⚠️ Error: Authorization token missing. Please log into Sahachari."
    token   = clean_auth_token(auth_token)
    headers = {"Authorization": token, "Content-Type": "application/json"}
    added_lines = []
    any_added   = False

    for item in items:
        product_id, matched_name = await find_product_id(item["item"], token)
        if not product_id:
            added_lines.append(f"❌ '{item['item']}' not found in Sahachari store.")
            continue

        unit    = item["unit"]
        raw_qty = item["quantity"] if item["quantity"] is not None else 1

        cart_quantity = int(raw_qty) if raw_qty == int(raw_qty) else raw_qty
        if cart_quantity < 1:
            cart_quantity = 1

        payload = {"productId": product_id, "quantity": cart_quantity}
        try:
            response = await http_client.post(
                f"{NESTJS_BACKEND_URL}/customer/cart",
                json=payload,
                headers=headers,
            )
            if response.status_code in (200, 201):
                qty_label = format_qty(item["quantity"], item["unit"]) if item["quantity"] is not None else "1 piece"
                added_lines.append(f"✅ {matched_name} — {qty_label} added!")
                any_added = True
            else:
                added_lines.append(f"❌ Failed to add {matched_name} ({response.status_code}).")
        except httpx.TimeoutException:
            added_lines.append(f"❌ Timed out adding {matched_name}. Please try again.")
        except httpx.ConnectError:
            added_lines.append(f"❌ Could not reach server adding {matched_name}. Please try again.")
        except Exception as e:
            added_lines.append(f"❌ Error on {item['item']} ({type(e).__name__}). Please try again.")

    if not added_lines:
        return "No items could be processed."

    result = "\n".join(added_lines)
    if any_added:
        cart_summary = await fetch_nestjs_cart_summary(token)
        result += f"\n\n{cart_summary}\n\n💡 Say 'checkout' to place your order or keep adding items!"
    else:
        result += "\n\nThis item isn't available in Sahachari's catalogue yet."
    return result

async def delete_from_nestjs_cart(item_name: str, auth_token: str) -> str:
    if not auth_token:
        return "⚠️ Error: Authorization token missing. Please log into Sahachari."
    token   = clean_auth_token(auth_token)
    headers = {"Authorization": token}
    try:
        response = await http_client.get(f"{NESTJS_BACKEND_URL}/customer/cart", headers=headers)
        if response.status_code != 200:
            return "❌ Could not fetch your cart."
        cart_data    = response.json()
        items        = cart_data.get("items", [])
        if not items:
            return "🛒 Your cart is already empty."
        target_item  = None
        matched_name = item_name
        for item in items:
            name = extract_product_name(item)
            if name != "Unknown Item" and (
                item_name.lower() in name.lower() or name.lower() in item_name.lower()
            ):
                target_item  = item
                matched_name = name
                break
        if not target_item:
            return f"❌ '{item_name}' not found in your cart."
        item_id      = target_item.get("_id") or target_item.get("id")
        del_response = await http_client.delete(
            f"{NESTJS_BACKEND_URL}/customer/cart/{item_id}",
            headers=headers,
        )
        if del_response.status_code in (200, 201, 204):
            cart_summary = await fetch_nestjs_cart_summary(token)
            return f"🗑️ {matched_name} removed from cart!\n\n{cart_summary}"
        return f"❌ Failed to remove {matched_name} ({del_response.status_code})"
    except Exception as e:
        return f"❌ Error removing item: {str(e)}"

async def forward_nestjs_order_placement(auth_token: str):
    if not auth_token:
        return "⚠️ Error: Authorization token missing. Please log into Sahachari.", False
    token = clean_auth_token(auth_token)
    try:
        cart_res = await http_client.get(
            f"{NESTJS_BACKEND_URL}/customer/cart",
            headers={"Authorization": token},
        )
        if cart_res.status_code == 200:
            items = cart_res.json().get("items", [])
            if not items:
                return "🛒 Your cart is empty. Add some items first!", False
        else:
            return "❌ Could not verify your cart right now. Please try again.", False
    except Exception:
        return "❌ Could not reach Sahachari server. Please try again shortly.", False
    return "🛒 Taking you to checkout now!", True

async def forward_nestjs_order_cancellation(auth_token: str) -> str:
    token = clean_auth_token(auth_token)
    try:
        orders_res = await http_client.get(
            f"{NESTJS_BACKEND_URL}/customer/orders",
            headers={"Authorization": token},
        )
        if orders_res.status_code == 200 and orders_res.json():
            last_order    = orders_res.json()[-1]
            last_order_id = last_order.get("id") or last_order.get("_id")
            cancel_res    = await http_client.post(
                f"{NESTJS_BACKEND_URL}/customer/orders/{last_order_id}/cancel",
                headers={"Authorization": token},
            )
            if cancel_res.status_code in (200, 201):
                return f"✅ Order {last_order_id} has been cancelled successfully."
            return f"❌ Could not cancel order ({cancel_res.status_code}). Please try from the Orders screen."
    except Exception as e:
        log.warning(f"forward_nestjs_order_cancellation failed: {e}")
    return "Failed to cancel order. Please check the Orders screen manually."

async def fetch_nestjs_order_status(auth_token: str) -> str:
    token = clean_auth_token(auth_token)
    try:
        response = await http_client.get(
            f"{NESTJS_BACKEND_URL}/customer/orders",
            headers={"Authorization": token},
        )
        if response.status_code == 200 and response.json():
            last     = response.json()[-1]
            status   = last.get("status", "Processing")
            order_id = last.get("_id") or last.get("id")
            icons    = {
                "Processing": "⏳", "Confirmed": "✅",
                "Out for Delivery": "🛵", "Delivered": "📦", "Cancelled": "❌",
            }
            return f"📦 Your last order ({order_id})\nStatus: {icons.get(status, '•')} {status}"
    except Exception as e:
        log.warning(f"fetch_nestjs_order_status failed: {e}")
    return "No orders found yet."

# ----------------------------------------------------------------------------
# Wishlist helpers
# ----------------------------------------------------------------------------

def _wishlist_line(item: dict) -> str:
    if item.get("quantity") is not None:
        return f"{item['item']} ({format_qty(item['quantity'], item.get('unit') or 'piece')})"
    return item["item"]

def add_to_wishlist(items: list, curr_session: dict) -> str:
    for new in items:
        if not any(w["item"].lower() == new["item"].lower() for w in curr_session["wishlist"]):
            curr_session["wishlist"].append(new.copy())
    count = len(curr_session["wishlist"])
    lines = [f"💛 Wishlist ({count} items)", "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    for idx, item in enumerate(curr_session["wishlist"], 1):
        lines.append(f"  {idx}. {_wishlist_line(item)}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def view_wishlist(curr_session: dict) -> str:
    if not curr_session["wishlist"]:
        return "Your wishlist is empty."
    lines = ["💛 Your Wishlist:"]
    for i, item in enumerate(curr_session["wishlist"], 1):
        lines.append(f"  {i}. {_wishlist_line(item)}")
    return "\n".join(lines)

def remove_from_wishlist(query: str, curr_session: dict) -> str:
    q = query.lower()
    if any(p in q for p in ["clear wishlist", "empty wishlist"]):
        curr_session["wishlist"].clear()
        return "💛 Your wishlist has been cleared."
    item_name = extract_item_name(query)
    if not item_name:
        return "Which item should I remove from your wishlist?"
    before = len(curr_session["wishlist"])
    curr_session["wishlist"] = [
        w for w in curr_session["wishlist"]
        if item_name.lower() not in w["item"].lower() and w["item"].lower() not in item_name.lower()
    ]
    if len(curr_session["wishlist"]) == before:
        return f"❌ '{item_name}' was not found in your wishlist."
    return f"🗑️ Removed '{item_name}' from your wishlist.\n\n{view_wishlist(curr_session)}"

# ----------------------------------------------------------------------------
# Product info / catalogue browsing
# ----------------------------------------------------------------------------

async def fetch_product_details(query: str, auth_token: str) -> str:
    if not auth_token:
        return "⚠️ Please log in to check product availability."

    token     = clean_auth_token(auth_token)
    item_name = extract_product_name_from_query(query)

    if not item_name:
        return "Which product would you like to know about? (e.g. 'Is apple available?')"

    clean_name = item_name.lower()
    search_terms = [
        item_name,
        item_name[:-1] if clean_name.endswith("s") else item_name + "s",
    ]

    try:
        products = []
        for term in search_terms:
            response = await http_client.get(
                f"{NESTJS_BACKEND_URL}/customer/products",
                params={"search": term},
                headers={"Authorization": token},
            )
            if response.status_code != 200:
                continue
            data = response.json()
            candidates = data if isinstance(data, list) else (
                data.get("data") or data.get("products") or data.get("items") or []
            )
            if candidates:
                products = candidates
                break

        if not products:
            return f"❌ '{item_name}' is not available in Sahachari's catalogue right now."
    
        query_words = set(w for w in re.findall(r"[a-z]+", item_name.lower()) if len(w) >= 3)
        matched = []
        for prod in products:
            name = prod.get("name", "")
            cand = name.lower()
            cand_words = set(w for w in re.findall(r"[a-z]+", cand) if len(w) >= 3)
            if item_name.lower() in cand or cand in item_name.lower() or len(query_words & cand_words) > 0:
                matched.append(prod)

        if not matched:
            return f"❌ '{item_name}' is not available in Sahachari right now."

        deduped     = {}
        store_cache = {}

        for prod in matched:
            key = (prod.get("name", "").lower(), str(prod.get("price", "")))
            if key not in deduped:
                deduped[key] = {"prod": prod.copy(), "total_stock": 0, "stores": []}
            deduped[key]["total_stock"] += prod.get("quantity", 0)
            store_id = prod.get("storeId", "")
            if isinstance(store_id, dict):
                store_name = store_id.get("name") or store_id.get("email") or "Unknown Store"
            elif isinstance(store_id, str) and store_id:
                store_name = await fetch_store_name_cache(store_id, token, store_cache)
            else:
                store_name = None
            if store_name and store_name not in deduped[key]["stores"]:
                deduped[key]["stores"].append(store_name)

        lines = []
        for _, entry in list(deduped.items())[:3]:
            prod             = entry["prod"]
            prod["quantity"] = entry["total_stock"]
            store_names      = entry["stores"]

            name        = prod.get("name", "Unknown")
            price       = prod.get("price", "N/A")
            final_price = prod.get("finalPrice")
            quantity    = prod.get("quantity", 0)
            description = prod.get("description", "")
            category    = prod.get("category", "")
            offers      = prod.get("offers", [])

            stock = f"✅ In Stock ({quantity} available)" if quantity > 0 else "❌ Out of Stock"

            price_clean = re.sub(r"[₹,\s]", "", str(price))
            price_num   = re.sub(r"/.*$", "", price_clean)
            try:
                final_num = float(final_price) if final_price else None
                base_num  = float(price_num) if price_num else None
            except (ValueError, TypeError):
                final_num = None
                base_num  = None

            if final_num and base_num and final_num != base_num:
                price_line = (
                    f"₹{int(final_num) if final_num == int(final_num) else final_num}"
                    f" (was ₹{int(base_num) if base_num == int(base_num) else base_num})"
                )
            elif price_num:
                unit_match = re.search(r"/(.+)$", price_clean)
                suffix     = f"/{unit_match.group(1)}" if unit_match else ""
                price_line = f"₹{price_num}{suffix}"
            else:
                price_line = f"₹{price}"

            active_offers = [o for o in offers if o.get("isActive")]
            offer_line    = ""
            if active_offers:
                o          = active_offers[0]
                offer_line = "\n  🏷️ Offer: " + (
                    f"{o['value']}% off" if o["type"] == "PERCENTAGE"
                    else f"₹{o['value']} flat off"
                )

            store_line = (
                f"\n  🏪 Store  : {store_names[0]}" if len(store_names) == 1
                else (f"\n  🏪 Stores : {', '.join(store_names)}" if store_names else "")
            )

            block = f"📦 {name}\n  💰 Price : {price_line}\n  📊 Stock : {stock}{store_line}"
            if category:
                block += f"\n  🗂️ Category: {category}"
            if description:
                block += f"\n  📝 {description}"
            block += offer_line
            lines.append(block)

        return "\n\n".join(lines) + "\n\nWould you like to add any of these to your cart?"

    except httpx.TimeoutException:
        return "❌ Request timed out. Please try again."
    except httpx.ConnectError:
        return "❌ Could not reach Sahachari server. Please try again shortly."
    except Exception as e:
        log.warning(f"fetch_product_details failed: {e}")
        return "❌ Could not fetch product details right now."

async def browse_catalog(query: str, auth_token: str) -> str:
    if not auth_token:
        return "⚠️ Please log in to browse the catalogue."

    token        = clean_auth_token(auth_token)
    q            = query.lower().strip()
    want_fruits  = any(x in q for x in CATEGORY_SYNONYMS["fruit"])
    want_veg     = any(x in q for x in CATEGORY_SYNONYMS["vegetable"])
    want_beverages = bool(re.search(r"\b(beverage|beverages|drink|drinks|juice|soft drinks?)\b", q))

    price_cap = None
    pm = re.search(r"(?:under|below|less than|at most|max|within)\s*(?:₹|rs\.?|rupees?)?\s*(\d+(?:\.\d+)?)", q)
    if pm:
        try:
            price_cap = float(pm.group(1))
        except Exception:
            pass

    sort_mode = None
    if re.search(r"\b(cheapest|lowest price|least expensive)\b", q):
        sort_mode = "asc"
    elif re.search(r"\b(most expensive|highest price|costliest)\b", q):
        sort_mode = "desc"

    stock_only = bool(re.search(r"\b(currently in stock|in stock|available)\b", q))

    try:
        response = await http_client.get(
            f"{NESTJS_BACKEND_URL}/customer/products",
            headers={"Authorization": token},
        )
        if response.status_code != 200:
            return "❌ Could not fetch catalogue right now. Please try again."

        data     = response.json()
        products = data if isinstance(data, list) else (
            data.get("data") or data.get("products") or data.get("items") or []
        )
        if not products:
            return "❌ The catalogue is empty right now."

        def norm_price(p):
            for key in ("finalPrice", "price"):
                v = p.get(key)
                if v is None:
                    continue
                try:
                    return float(re.sub(r"[^0-9.]", "", str(v)) or 0)
                except Exception:
                    pass
            return None

        filtered = []
        for p in products:
            name     = str(p.get("name", ""))
            category = str(p.get("category", "")).lower()
            pname    = name.lower()

            # Category field is often a combined string like "Vegetables and Fruits"
        # for every product in that group, so it can't reliably distinguish
        # fruit from vegetable. Classify by product name against known lists
        # instead.
        KNOWN_FRUITS = {
            "mango", "apple", "banana", "orange", "grape", "papaya",
            "pineapple", "watermelon", "guava", "pomegranate", "lemon",
            "lime", "melon", "kiwi", "chikoo", "sapota", "jackfruit",
        }
        KNOWN_VEGETABLES = {
            "onion", "carrot", "tomato", "potato", "cabbage", "cauliflower",
            "brinjal", "eggplant", "spinach", "methi", "palak", "coriander",
            "beans", "peas", "cucumber", "capsicum", "pepper", "ladies finger",
            "okra", "beetroot", "radish", "garlic", "ginger", "gourd", "drumstick",
        }

        for p in products:
            name  = str(p.get("name", ""))
            pname = name.lower().strip()
            is_fruit = any(f in pname for f in KNOWN_FRUITS)
            is_veg   = any(v in pname for v in KNOWN_VEGETABLES)

            if want_fruits and not is_fruit:
                continue
            if want_veg and not is_veg:
                continue
            if want_beverages and not (
                "beverage" in pname or "drink" in pname or "juice" in pname
                or "beverage" in category or "drink" in category or "juice" in category
            ):
                continue
            if price_cap is not None:
                pv = norm_price(p)
                if pv is None or pv > price_cap:
                    continue
            if stock_only and (p.get("quantity", 0) or 0) <= 0:
                continue
            filtered.append(p)

        if sort_mode == "asc":
            filtered.sort(key=lambda x: norm_price(x) if norm_price(x) is not None else float("inf"))
        elif sort_mode == "desc":
            filtered.sort(key=lambda x: norm_price(x) if norm_price(x) is not None else float("-inf"), reverse=True)

        if not filtered:
            return "❌ No matching items were found in the catalogue for that filter."

        lines = []
        for p in filtered[:20]:
            name  = p.get("name", "Unknown")
            price = p.get("finalPrice") or p.get("price") or "N/A"
            qty   = p.get("quantity", 0)
            stock_line = f"✅ {qty} in stock" if qty and qty > 0 else "❌ Out of stock"
            block = f"📦 {name}\n   💰 ₹{price}   {stock_line}"
            lines.append(block)

        if want_fruits:
            header = "Here are the available fruits:"
        elif want_veg and price_cap is not None:
            header = f"Here are the vegetables under ₹{int(price_cap) if price_cap == int(price_cap) else price_cap}:"
        elif want_veg:
            header = "Here are the available vegetables:"
        elif want_beverages:
            header = "Here are the available beverages:"
        elif price_cap is not None:
            header = f"Here are the items under ₹{int(price_cap) if price_cap == int(price_cap) else price_cap}:"
        elif sort_mode == "asc":
            header = "Here are the cheapest matching items:"
        elif sort_mode == "desc":
            header = "Here are the most expensive matching items:"
        elif stock_only:
            header = "Here are the items currently in stock:"
        else:
            header = "Here are the matching items:"

        return header + "\n" + "\n".join(lines)

    except httpx.TimeoutException:
        return "❌ Request timed out. Please try again."
    except httpx.ConnectError:
        return "❌ Could not reach Sahachari server. Please try again shortly."
    except Exception as e:
        log.warning(f"browse_catalog failed: {e}")
        return "❌ Could not fetch catalogue right now."

# ----------------------------------------------------------------------------
# RAG
# ----------------------------------------------------------------------------

async def get_rag_response(query: str) -> str:
    if collection is None or embedding_model is None:
        return (
            "ℹ️ My knowledge base isn't loaded right now. "
            "Is there a specific grocery item or order I can help you with?"
        )
    try:
        query_vector = embedding_model.encode(query).tolist()
        results      = collection.query(query_embeddings=[query_vector], n_results=4)

        if not results or not results.get("documents") or not results["documents"][0]:
            return "ℹ️ I'm not quite sure about that. Is there a specific grocery item or order I can help you with?"

        chunks = results["documents"][0]

        if reranker is not None:
            scores = reranker.compute_score([[query, chunk] for chunk in chunks])
            if isinstance(scores, float):
                scores = [scores]
            ranked_chunks   = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
            top_chunk, top_score = ranked_chunks[0]
            log.info(f"RAG top score: {top_score:.3f} for query: {query!r}")
            if top_score < RELEVANCE_THRESHOLD:
                return "ℹ️ I don't have exact information on that right now. Can I help you with something else?"
        else:
            top_chunk = chunks[0]

        cleaned = re.sub(r"#[^\n]*\n?", "", top_chunk)
        cleaned = re.sub(r"^={5,}.*?={5,}\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"-{5,}", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        context = cleaned.strip()

        if qwen_pipeline is not None:
            loop     = asyncio.get_running_loop()
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are Sahachari assistant. Read the provided Context carefully. "
                        "Write a polite, concise, helpful answer to the user's Question. "
                        "If the context doesn't answer the question, say you're not sure rather than guessing."
                    ),
                },
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
            ]

            def generate_text():
                return qwen_pipeline(
                    messages,
                    max_new_tokens=150,
                    return_full_text=False,
                    temperature=0.3,
                    do_sample=True,
                )[0]["generated_text"]

            return (await loop.run_in_executor(None, generate_text)).strip()

        return context

    except Exception as e:
        log.exception(f"get_rag_response failed for query={query!r}")
        return "ℹ️ I'm having trouble retrieving that right now. How can I help you with your shopping?"

# ----------------------------------------------------------------------------
# Chat endpoint
# ----------------------------------------------------------------------------

class ChatRequest(BaseModel):
    query: str
    session_id: str

@app.post("/chat")
async def chat_endpoint(req: ChatRequest, authorization: str = Header(None)):
    query                = req.query.strip()
    session_id           = req.session_id
    current_user_session = await session_store.get(session_id)
    cart_updated         = False

    try:
        # ── Pending quantity reply ─────────────────────────────────────────
        if current_user_session["pending_item"] is not None:
            quantity, unit = parse_quantity_reply(query)
            pending = current_user_session["pending_item"]
            intent  = current_user_session["pending_intent"]
            pending_resolved = True

            if quantity is not None:
                pending["quantity"] = quantity
                pending["unit"]     = unit
                current_user_session["pending_item"]   = None
                current_user_session["pending_intent"] = None
                if intent == "wishlist":
                    response_text = add_to_wishlist([pending], current_user_session)
                else:
                    response_text = await forward_to_nestjs_cart([pending], authorization)
                    cart_updated  = True
            else:
                # Not a quantity reply. Before trapping the user in a
                # re-prompt loop, check whether this message clearly looks
                # like an unrelated new request (e.g. "do you have chicken
                # burger", "show my cart"). If it does, drop the pending
                # item and let it fall through to normal intent routing
                # instead of mis-attaching it to the old pending item.
                new_intent, new_confidence = detect_intent(query)
                if new_confidence >= 1.0 and new_intent not in ("order", "wishlist"):
                    current_user_session["pending_item"]   = None
                    current_user_session["pending_intent"] = None
                    pending_resolved = False
                else:
                    response_text = (
                        f"Sorry, I didn't catch that. "
                        f"How much {pending['item']} would you like? (e.g. '1 kg', '500 g', '2 pieces')"
                    )

            if pending_resolved:
                await session_store.save(session_id, current_user_session)
                return {"response": response_text, "cart_updated": cart_updated}
            # else: fall through to normal intent routing below using the
            # already-cleared pending state.

        # ── Normal intent routing ──────────────────────────────────────────
        intent, confidence = detect_intent(query)
        # Qwen's intent guesses have proven unreliable in testing (e.g. guessing
        # "status" or "cancel" for unrelated "how do I order X" questions, which
        # can trigger real destructive actions like order cancellation). Rather
        # than trusting a weak guess, low-confidence messages go straight to RAG,
        # where a cautious "I'm not sure" is far safer than a wrong, confident
        # action being executed against the backend.
        if confidence < 0.5:
            intent = "rag"

        if intent == "greeting":
            response_text = "Namaste! Welcome to Sahachari 🛒\nWhat can I get for you today?"

        elif intent == "courtesy":
            response_text = "You're very welcome! 😊 Always happy to help you shop fresh with Sahachari."

        elif intent == "view_cart":
            response_text = await fetch_nestjs_cart_summary(authorization)

        elif intent == "wishlist_remove":
            response_text = remove_from_wishlist(query, current_user_session)

        elif intent == "wishlist":
            if any(p in query.lower() for p in ["show", "view", "my wishlist", "see"]):
                response_text = view_wishlist(current_user_session)
            else:
                items = extract_grocery_items(query)
                if items:
                    missing_qty = [i for i in items if i["quantity"] is None]
                    has_qty     = [i for i in items if i["quantity"] is not None]
                    lines       = []
                    if has_qty:
                        lines.append(add_to_wishlist(has_qty, current_user_session))
                    if missing_qty:
                        pending = missing_qty[0]
                        current_user_session["pending_item"]   = pending
                        current_user_session["pending_intent"] = "wishlist"
                        lines.append(f"How much {pending['item']} would you like to save? (e.g. '1 kg', '2 pieces')")
                    response_text = "\n\n".join(lines)
                else:
                    response_text = "Tell me what to save, e.g. add 1 kg apples to wishlist."

        elif intent == "status":
            response_text = await fetch_nestjs_order_status(authorization)

        elif intent == "cancel":
            response_text = await forward_nestjs_order_cancellation(authorization)
            cart_updated  = True   # FIX: was missing

        elif intent == "delete_cart":
            item_name = extract_item_name(query)
            if item_name:
                response_text = await delete_from_nestjs_cart(item_name, authorization)
                cart_updated  = True
            else:
                response_text = "Which item would you like to remove? (e.g. 'remove onion from cart')"

        elif intent == "checkout":
            response_text, cart_updated = await forward_nestjs_order_placement(authorization)

        elif intent == "browse":
            response_text = await browse_catalog(query, authorization)

        elif intent == "product_info":
            response_text = await fetch_product_details(query, authorization)

        elif intent == "order":
            if "wishlist" in query.lower():
                if current_user_session["wishlist"]:
                    response_text = await forward_to_nestjs_cart(
                        current_user_session["wishlist"], authorization
                    )
                    current_user_session["wishlist"].clear()
                    cart_updated = True
                else:
                    response_text = "Your wishlist is empty. Nothing to add!"
            else:
                items = extract_grocery_items(query)
                if items:
                    missing_qty = [i for i in items if i["quantity"] is None]
                    has_qty     = [i for i in items if i["quantity"] is not None]
                    lines       = []
                    if has_qty:
                        res = await forward_to_nestjs_cart(has_qty, authorization)
                        lines.append(res)
                        cart_updated = True
                    if missing_qty:
                        pending = missing_qty[0]
                        current_user_session["pending_item"]   = pending
                        current_user_session["pending_intent"] = "order"
                        lines.append(f"How much {pending['item']} would you like? (e.g. '1 kg', '500 g')")
                    response_text = "\n\n".join(lines)
                else:
                    response_text = "I couldn't figure out which items you'd like. Try: 'I want 2 kg onions'."

        else:
            response_text = await get_rag_response(query)

        await session_store.save(session_id, current_user_session)
        return {"response": response_text, "cart_updated": cart_updated}

    except Exception as e:
        log.exception("chat_endpoint failed")
        return {"response": f"System Error: {str(e)}", "cart_updated": False}

if __name__ == "__main__":
    log.info("Starting Sahachari AI Service...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
