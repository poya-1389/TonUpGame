"""TonUp backend, phase 1: auth, ledger, tasks, gift codes, referrals, leaderboard, admin bot.
All money is stored as integer nanoTON. Balance changes ONLY via post_tx (ledger)."""
import asyncio, hashlib, hmac, json, os, time, logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import jwt
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           Message, WebAppInfo)
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import (BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func, select)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

log = logging.getLogger("tonup")
logging.basicConfig(level=logging.INFO)

# ---------- config ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "TONUP_BOT")
JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-me")
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()}
DEV_MODE = os.environ.get("DEV_MODE") == "1"  # skips initData check locally ONLY
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")
NANO = 10**9
DB_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./tonup.db")
if DB_URL.startswith("postgres://"): DB_URL = DB_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DB_URL.startswith("postgresql://"): DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DB_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)
now = lambda: datetime.now(timezone.utc)
def ton(n: int) -> str: return f"{n / NANO:.3f}"

# ---------- models ----------
class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str] = mapped_column(String(2), default="fa")
    balance: Mapped[int] = mapped_column(BigInteger, default=0)
    total_earned: Mapped[int] = mapped_column(BigInteger, default=0, index=True)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    referred_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[int] = mapped_column(BigInteger)  # signed
    balance_after: Mapped[int] = mapped_column(BigInteger)
    idem_key: Mapped[str] = mapped_column(String(128), unique=True)
    meta: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(24))  # join_channel|join_group|visit_link|start_bot|view_content
    target: Mapped[str] = mapped_column(String(300))  # @channel or URL
    reward: Mapped[int] = mapped_column(BigInteger)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class TaskCompletion(Base):
    __tablename__ = "task_completions"
    __table_args__ = (UniqueConstraint("user_id", "task_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class GiftCode(Base):
    __tablename__ = "gift_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    reward: Mapped[int] = mapped_column(BigInteger)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    per_user: Mapped[int] = mapped_column(Integer, default=1)
    used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class GiftClaim(Base):
    __tablename__ = "gift_code_claims"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_id: Mapped[int] = mapped_column(ForeignKey("gift_codes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Referral(Base):
    __tablename__ = "referrals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    referred_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

class AdminLog(Base):
    __tablename__ = "admin_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_tg_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

DEFAULTS = {"maintenance": False, "ref_normal": 1 * NANO, "ref_active": 2_500_000_000,
            "active_min_tasks": 1}

async def get_setting(s: AsyncSession, key: str):
    row = await s.get(Setting, key)
    return json.loads(row.value) if row else DEFAULTS[key]

async def set_setting(s: AsyncSession, key: str, value):
    row = await s.get(Setting, key)
    if row: row.value = json.dumps(value)
    else: s.add(Setting(key=key, value=json.dumps(value)))

# ---------- ledger ----------
async def post_tx(s: AsyncSession, user_id: int, type_: str, amount: int,
                  idem_key: str, meta: dict | None = None) -> bool:
    """Only way to change a balance. Idempotent: same idem_key applies once.
    Returns False if duplicate. Raises ValueError on insufficient funds."""
    if (await s.execute(select(Transaction.id).where(Transaction.idem_key == idem_key))).first():
        return False
    user = (await s.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    new_bal = user.balance + amount
    if new_bal < 0: raise ValueError("insufficient")
    user.balance = new_bal
    if amount > 0 and type_ not in ("deposit", "refund"): user.total_earned += amount
    s.add(Transaction(user_id=user_id, type=type_, amount=amount, balance_after=new_bal,
                      idem_key=idem_key, meta=json.dumps(meta or {})))
    await s.flush()
    log.info("TX user=%s %s %+d", user_id, type_, amount)
    return True

# ---------- telegram auth ----------
def validate_init_data(init_data: str, max_age: int = 86400) -> dict:
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", None)
    if not received: raise ValueError("no hash")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received): raise ValueError("bad hash")
    if time.time() - int(pairs.get("auth_date", 0)) > max_age: raise ValueError("expired")
    pairs["user"] = json.loads(pairs["user"])
    return pairs

def make_token(uid: int) -> str:
    return jwt.encode({"uid": uid, "exp": int(time.time()) + 86400}, JWT_SECRET, "HS256")

async def db():
    async with Session() as s:
        yield s

async def current_user(request: Request, s: AsyncSession = Depends(db)) -> User:
    h = request.headers.get("authorization", "")
    try: uid = jwt.decode(h.removeprefix("Bearer "), JWT_SECRET, ["HS256"])["uid"]
    except Exception: raise HTTPException(401, "unauthorized")
    u = await s.get(User, uid)
    if not u or u.banned: raise HTTPException(403, "forbidden")
    if await get_setting(s, "maintenance") and u.tg_id not in ADMIN_IDS:
        raise HTTPException(503, "maintenance")
    return u

# ---------- rate limit (in-memory; swap to Redis when scaling to >1 instance) ----------
_hits: dict[str, list[float]] = {}
def rate_limit(key: str, n: int, per: int = 60):
    t = time.time(); lst = [x for x in _hits.get(key, []) if t - x < per]
    if len(lst) >= n: raise HTTPException(429, "slow_down")
    lst.append(t); _hits[key] = lst

# ---------- referral logic ----------
async def maybe_activate_referral(s: AsyncSession, user: User):
    ref = (await s.execute(select(Referral).where(Referral.referred_id == user.id))).scalar_one_or_none()
    if not ref or ref.active: return
    need = await get_setting(s, "active_min_tasks")
    done = (await s.execute(select(func.count()).select_from(TaskCompletion)
                            .where(TaskCompletion.user_id == user.id))).scalar_one()
    if done >= need:
        ref.active = True
        await post_tx(s, ref.referrer_id, "referral", await get_setting(s, "ref_active"),
                      f"refactive:{user.id}", {"friend": user.id})

# ---------- app ----------
bot = Bot(BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher()

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    task = asyncio.create_task(dp.start_polling(bot)) if bot else None
    yield
    if task: task.cancel()

app = FastAPI(title="TonUp API", lifespan=lifespan)

@app.exception_handler(Exception)
async def hide_errors(request: Request, exc: Exception):
    log.exception("unhandled")
    return JSONResponse({"error": "server_error"}, status_code=500)

def user_dto(u: User) -> dict:
    return {"id": u.id, "tg_id": u.tg_id, "name": f"{u.first_name} {u.last_name}".strip(),
            "username": u.username, "photo": u.photo_url, "balance": u.balance / NANO,
            "earned": u.total_earned / NANO, "lang": u.lang}

class AuthIn(BaseModel):
    init_data: str = Field(max_length=4096)

@app.post("/api/auth")
async def auth(body: AuthIn, request: Request, s: AsyncSession = Depends(db)):
    rate_limit(f"auth:{request.client.host}", 20)
    try:
        data = validate_init_data(body.init_data)
    except Exception:
        raise HTTPException(401, "invalid_init_data")
    tu = data["user"]
    u = (await s.execute(select(User).where(User.tg_id == tu["id"]))).scalar_one_or_none()
    if not u:
        u = User(tg_id=tu["id"], first_name=tu.get("first_name", ""), last_name=tu.get("last_name", ""),
                 username=tu.get("username"), photo_url=tu.get("photo_url"))
        sp = data.get("start_param", "")
        if sp.startswith("ref_") and sp[4:].isdigit():
            referrer = (await s.execute(select(User).where(User.tg_id == int(sp[4:])))).scalar_one_or_none()
            if referrer and referrer.tg_id != tu["id"]:  # no self-referral
                u.referred_by = referrer.id
        s.add(u); await s.flush()
        if u.referred_by:
            s.add(Referral(referrer_id=u.referred_by, referred_id=u.id))
            await post_tx(s, u.referred_by, "referral", await get_setting(s, "ref_normal"),
                          f"refnormal:{u.id}", {"friend": u.id})
    else:
        u.first_name, u.last_name = tu.get("first_name", ""), tu.get("last_name", "")
        u.username, u.photo_url = tu.get("username"), tu.get("photo_url")
    if u.banned: raise HTTPException(403, "forbidden")
    await s.commit()
    return {"token": make_token(u.id), "user": user_dto(u),
            "maintenance": await get_setting(s, "maintenance") and u.tg_id not in ADMIN_IDS}

@app.get("/api/me")
async def me(u: User = Depends(current_user)): return user_dto(u)

@app.get("/api/tasks")
async def tasks(u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    t = now()
    rows = (await s.execute(select(Task).where(Task.active == True))).scalars().all()
    done = {r for (r,) in (await s.execute(select(TaskCompletion.task_id)
            .where(TaskCompletion.user_id == u.id))).all()}
    def ok(x):
        return (not x.starts_at or x.starts_at <= t) and (not x.ends_at or x.ends_at >= t)
    return [{"id": x.id, "title": x.title, "description": x.description, "type": x.type,
             "target": x.target, "reward": x.reward / NANO, "done": x.id in done}
            for x in rows if ok(x)]

@app.post("/api/tasks/{task_id}/claim")
async def claim_task(task_id: int, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    rate_limit(f"claim:{u.id}", 10)
    t = await s.get(Task, task_id)
    if not t or not t.active: raise HTTPException(404, "not_found")
    if (await s.execute(select(TaskCompletion).where(TaskCompletion.user_id == u.id,
            TaskCompletion.task_id == t.id))).first(): raise HTTPException(409, "already_done")
    if t.type in ("join_channel", "join_group"):  # real membership check via Telegram
        try:
            m = await bot.get_chat_member(t.target, u.tg_id)
            if m.status not in ("member", "administrator", "creator"): raise HTTPException(400, "not_member")
        except HTTPException: raise
        except Exception: raise HTTPException(400, "cannot_verify")
    s.add(TaskCompletion(user_id=u.id, task_id=t.id))
    await post_tx(s, u.id, "task_reward", t.reward, f"task:{u.id}:{t.id}", {"task": t.id})
    await maybe_activate_referral(s, u)
    await s.commit()
    return {"reward": t.reward / NANO, "balance": u.balance / NANO}

class GiftIn(BaseModel):
    code: str = Field(min_length=2, max_length=64)

@app.post("/api/gift")
async def redeem(body: GiftIn, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    rate_limit(f"gift:{u.id}", 5)
    g = (await s.execute(select(GiftCode).where(GiftCode.code == body.code.strip().upper())
                         .with_for_update())).scalar_one_or_none()
    if not g or not g.active: raise HTTPException(404, "invalid_code")
    if g.expires_at and g.expires_at < now(): raise HTTPException(410, "expired")
    if g.used >= g.max_uses: raise HTTPException(410, "exhausted")
    mine = (await s.execute(select(func.count()).select_from(GiftClaim)
            .where(GiftClaim.code_id == g.id, GiftClaim.user_id == u.id))).scalar_one()
    if mine >= g.per_user: raise HTTPException(409, "limit_reached")
    g.used += 1
    s.add(GiftClaim(code_id=g.id, user_id=u.id))
    await post_tx(s, u.id, "gift_code", g.reward, f"gift:{g.id}:{u.id}:{mine}", {"code": g.code})
    await s.commit()
    return {"reward": g.reward / NANO, "balance": u.balance / NANO}

@app.get("/api/referrals")
async def referrals(u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    rows = (await s.execute(select(Referral, User).join(User, User.id == Referral.referred_id)
            .where(Referral.referrer_id == u.id).order_by(Referral.id.desc()).limit(100))).all()
    n, a = await get_setting(s, "ref_normal"), await get_setting(s, "ref_active")
    friends = [{"name": x.first_name, "active": r.active,
                "reward": (n + (a if r.active else 0)) / NANO} for r, x in rows]
    active = sum(1 for f in friends if f["active"])
    return {"link": f"https://t.me/{BOT_USERNAME}/app?startapp=ref_{u.tg_id}",
            "total": len(friends), "active": active,
            "pending": (len(friends) - active) * a / NANO,
            "earned": sum(f["reward"] for f in friends), "friends": friends}

@app.get("/api/leaderboard")
async def leaderboard(kind: str = "earners", u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    col = User.total_earned if kind == "earners" else User.balance
    top = (await s.execute(select(User).where(User.banned == False).order_by(col.desc()).limit(23))).scalars().all()
    mine = getattr(u, "total_earned" if kind == "earners" else "balance")
    rank = (await s.execute(select(func.count()).select_from(User)
            .where(col > mine, User.banned == False))).scalar_one() + 1
    val = lambda x: getattr(x, "total_earned" if kind == "earners" else "balance") / NANO
    return {"top": [{"rank": i + 1, "name": x.first_name, "photo": x.photo_url, "value": val(x)}
                    for i, x in enumerate(top)],
            "me": {"rank": rank, "value": mine / NANO}}

@app.get("/api/transactions")
async def txs(u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    rows = (await s.execute(select(Transaction).where(Transaction.user_id == u.id)
            .order_by(Transaction.id.desc()).limit(50))).scalars().all()
    return [{"type": r.type, "amount": r.amount / NANO, "at": r.created_at.isoformat()} for r in rows]

@app.get("/api/health")
async def health(): return {"ok": True}

@app.get("/")
async def index(): return FileResponse(os.path.join(os.path.dirname(__file__), "index.html"))

# ---------- bot ----------
def is_admin(uid: int) -> bool: return uid in ADMIN_IDS

@dp.message(CommandStart())
async def start(m: Message):
    arg = m.text.split(maxsplit=1)[1] if len(m.text.split()) > 1 else ""
    url = WEBAPP_URL + (f"?startapp={arg}" if arg else "")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 TonUp", web_app=WebAppInfo(url=url))]])
    await m.answer("🚀 TonUp\nبازی کن، وظیفه انجام بده، TON جمع کن.", reply_markup=kb)

PANEL = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📊 Statistics", callback_data="p:stats"),
     InlineKeyboardButton(text="👥 Users", callback_data="p:users")],
    [InlineKeyboardButton(text="🎯 Tasks", callback_data="p:tasks"),
     InlineKeyboardButton(text="🎁 Gift Codes", callback_data="p:gifts")],
    [InlineKeyboardButton(text="💰 Finance", callback_data="p:fin"),
     InlineKeyboardButton(text="⚙️ Settings", callback_data="p:set")]])

HELP = {
 "users": "/user <tg_id>\n/ban <tg_id>\n/unban <tg_id>",
 "tasks": "/addtask <type> <@target|url> <reward> <title...>\ntypes: join_channel join_group visit_link start_bot view_content\n/deltask <id>\n/pausetask <id>\n/resumetask <id>\n/tasks",
 "gifts": "/addgift <CODE> <reward> <max_uses> [per_user=1]",
 "fin": "/credit <tg_id> <amount> <reason...>\n/debit <tg_id> <amount> <reason...>",
 "set": "/maintenance on|off\n/setref <normal> <active>\n/setactive <min_tasks>"}

@dp.message(Command("panel"))
async def panel(m: Message):
    if not is_admin(m.from_user.id): return  # silent for non-admins
    await m.answer("🛡 TonUp Admin", reply_markup=PANEL)

@dp.callback_query(F.data.startswith("p:"))
async def panel_cb(c: CallbackQuery):
    if not is_admin(c.from_user.id): return await c.answer()
    key = c.data[2:]
    if key == "stats":
        async with Session() as s:
            users = (await s.execute(select(func.count()).select_from(User))).scalar_one()
            new = (await s.execute(select(func.count()).select_from(User)
                   .where(User.created_at > now() - timedelta(days=1)))).scalar_one()
            dist = (await s.execute(select(func.coalesce(func.sum(Transaction.amount), 0))
                    .where(Transaction.amount > 0, Transaction.type != "deposit"))).scalar_one()
            done = (await s.execute(select(func.count()).select_from(TaskCompletion))).scalar_one()
            refs = (await s.execute(select(func.count()).select_from(Referral))).scalar_one()
        text = f"📊 Users: {users}\nNew 24h: {new}\nTON distributed: {ton(dist)}\nTasks done: {done}\nReferrals: {refs}"
    else:
        text = HELP.get(key, "-")
    await c.message.answer(text); await c.answer()

async def admin_log(s, m: Message, action: str):
    s.add(AdminLog(admin_tg_id=m.from_user.id, action=action))

async def by_tg(s, tg: str):
    return (await s.execute(select(User).where(User.tg_id == int(tg)))).scalar_one_or_none()

@dp.message(Command("user"))
async def cmd_user(m: Message):
    if not is_admin(m.from_user.id): return
    async with Session() as s:
        u = await by_tg(s, m.text.split()[1])
        if not u: return await m.answer("not found")
        await m.answer(f"{u.first_name} @{u.username}\nID {u.tg_id}\nBalance {ton(u.balance)}\nEarned {ton(u.total_earned)}\nBanned {u.banned}")

@dp.message(Command("ban", "unban"))
async def cmd_ban(m: Message):
    if not is_admin(m.from_user.id): return
    cmd, tg = m.text.split()[:2]
    async with Session() as s:
        u = await by_tg(s, tg)
        if not u: return await m.answer("not found")
        u.banned = cmd.startswith("/ban")
        await admin_log(s, m, f"{cmd} {tg}"); await s.commit()
    await m.answer("done")

@dp.message(Command("credit", "debit"))
async def cmd_money(m: Message):
    if not is_admin(m.from_user.id): return
    parts = m.text.split(maxsplit=3)
    if len(parts) < 4: return await m.answer("need reason")
    cmd, tg, amt, reason = parts
    amount = int(float(amt) * NANO) * (1 if cmd == "/credit" else -1)
    async with Session() as s:
        u = await by_tg(s, tg)
        if not u: return await m.answer("not found")
        try:
            await post_tx(s, u.id, "admin_adjustment", amount,
                          f"admin:{m.chat.id}:{m.message_id}", {"admin": m.from_user.id, "reason": reason})
        except ValueError: return await m.answer("insufficient balance")
        await admin_log(s, m, f"Admin {m.from_user.id} {cmd} {amt} TON user {tg}: {reason}")
        await s.commit()
    await m.answer("done")

@dp.message(Command("addgift"))
async def cmd_gift(m: Message):
    if not is_admin(m.from_user.id): return
    p = m.text.split()
    async with Session() as s:
        s.add(GiftCode(code=p[1].upper(), reward=int(float(p[2]) * NANO), max_uses=int(p[3]),
                       per_user=int(p[4]) if len(p) > 4 else 1))
        await admin_log(s, m, f"addgift {p[1]}"); await s.commit()
    await m.answer(f"ok\nhttps://t.me/{BOT_USERNAME}/app?startapp=gift_{p[1].upper()}")

@dp.message(Command("addtask"))
async def cmd_addtask(m: Message):
    if not is_admin(m.from_user.id): return
    p = m.text.split(maxsplit=4)
    async with Session() as s:
        s.add(Task(type=p[1], target=p[2], reward=int(float(p[3]) * NANO), title=p[4]))
        await admin_log(s, m, f"addtask {p[4]}"); await s.commit()
    await m.answer("ok")

@dp.message(Command("tasks"))
async def cmd_tasks(m: Message):
    if not is_admin(m.from_user.id): return
    async with Session() as s:
        rows = (await s.execute(select(Task))).scalars().all()
    await m.answer("\n".join(f"#{t.id} {'✅' if t.active else '⏸'} {t.title} +{ton(t.reward)}" for t in rows) or "empty")

@dp.message(Command("deltask", "pausetask", "resumetask"))
async def cmd_taskops(m: Message):
    if not is_admin(m.from_user.id): return
    cmd, tid = m.text.split()[:2]
    async with Session() as s:
        t = await s.get(Task, int(tid))
        if not t: return await m.answer("not found")
        if cmd == "/deltask": t.active = False  # soft delete keeps completion history
        else: t.active = cmd == "/resumetask"
        await admin_log(s, m, f"{cmd} {tid}"); await s.commit()
    await m.answer("done")

@dp.message(Command("maintenance", "setref", "setactive"))
async def cmd_settings(m: Message):
    if not is_admin(m.from_user.id): return
    p = m.text.split()
    async with Session() as s:
        if p[0] == "/maintenance": await set_setting(s, "maintenance", p[1] == "on")
        elif p[0] == "/setref":
            await set_setting(s, "ref_normal", int(float(p[1]) * NANO))
            await set_setting(s, "ref_active", int(float(p[2]) * NANO))
        else: await set_setting(s, "active_min_tasks", int(p[1]))
        await admin_log(s, m, m.text); await s.commit()
    await m.answer("done")
