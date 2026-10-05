"""TonUp phase 2: Game engine. Plug-in module: run with `uvicorn games:app`.
Every game is server-side. Each round = one GameSession (resolved exactly once).
Randomness is provably fair: sha256(seed) is shown BEFORE play, seed is revealed AFTER;
all outcomes are derived from HMAC(seed, label), so anyone can re-verify them."""
import hashlib, hmac, json, math, os, secrets, time, uuid
from datetime import datetime, timedelta, timezone

from aiogram.filters import Command
from aiogram.types import Message
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

import main
from main import (NANO, AdminLog, Base, Session, Setting, User, admin_log, app, current_user,
                  db, dp, is_admin, log, now, post_tx, rate_limit)

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- config (all editable live from the bot with /setgame) ----------
WHEEL_LOW = [{"mult": 0, "weight": 30}, {"mult": 0.5, "weight": 20}, {"mult": 1, "weight": 20},
             {"mult": 1.5, "weight": 14}, {"mult": 2, "weight": 10}, {"mult": 3, "weight": 4},
             {"mult": 5, "weight": 1.6}, {"mult": 10, "weight": 0.4}]          # RTP 95%
WHEEL_HIGH = [{"mult": 0, "weight": 32}, {"mult": 0.5, "weight": 20}, {"mult": 1, "weight": 19},
              {"mult": 1.5, "weight": 14}, {"mult": 2, "weight": 8.5}, {"mult": 3, "weight": 3.5},
              {"mult": 5, "weight": 2}, {"mult": 10, "weight": 1}]              # RTP 97.5%, used for stake >= 5
CFG = {
    "daily_on": True,
    "daily_prizes": [{"tier": "very_low", "amount": 0.01, "weight": 50}, {"tier": "low", "amount": 0.03, "weight": 30},
                     {"tier": "medium", "amount": 0.1, "weight": 13}, {"tier": "high", "amount": 0.3, "weight": 5},
                     {"tier": "very_high", "amount": 1.0, "weight": 2}],
    "wheel_low": WHEEL_LOW, "wheel_high": WHEEL_HIGH, "wheel_split": 5,
    "crash_on": True, "crash_min": 0.1, "crash_max": 10, "crash_growth": 0.08, "crash_grace_ms": 200,
    "bomb_on": True, "bomb_min": 0.1, "bomb_max": 10, "bomb_edge": 0.97,
    "arena_on": True, "arena_min": 0.5, "arena_max": 10, "arena_win_mult": 1.9,
    "wheel_on": True, "wheel_min": 1, "wheel_max": 10,
    "max_payout": 100,
}

async def gs(s: AsyncSession, key: str):
    row = await s.get(Setting, key)
    return json.loads(row.value) if row else CFG[key]

def rtp(table) -> float:
    tw = sum(r["weight"] for r in table)
    return sum(r["mult"] * r["weight"] for r in table) / tw

# ---------- models ----------
class GameSession(Base):
    __tablename__ = "game_sessions"
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    game: Mapped[str] = mapped_column(String(16), index=True)
    stake: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)
    payout: Mapped[int] = mapped_column(BigInteger, default=0)
    seed: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(Text, default="{}")
    request_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class DailySpin(Base):
    __tablename__ = "daily_spins"
    __table_args__ = (UniqueConstraint("user_id", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    day: Mapped[str] = mapped_column(String(10))
    tier: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

# ---------- provably-fair randomness ----------
def rnd(seed: str, label: str) -> float:
    h = hmac.new(seed.encode(), label.encode(), hashlib.sha256).hexdigest()
    return int(h[:13], 16) / 2**52

def pick(seed: str, label: str, weights: list[float]) -> int:
    x, acc = rnd(seed, label) * sum(weights), 0.0
    for i, w in enumerate(weights):
        acc += w
        if x < acc: return i
    return len(weights) - 1

def crash_point(seed: str) -> float:
    h = int(hmac.new(seed.encode(), b"crash", hashlib.sha256).hexdigest()[:13], 16); e = 2**52
    if h % 33 == 0: return 1.0                      # ~3% instant crash = house edge
    return min(1000.0, math.floor((100 * e - h) / (e - h)) / 100)

def mult_at(elapsed: float, growth: float) -> float:
    return math.floor(100 * math.exp(growth * max(elapsed, 0))) / 100

def bomb_mult(k: int, n: int, edge: float) -> float:
    return 1.0 if k == 0 else math.floor(100 * edge * math.comb(25, k) / math.comb(25 - n, k)) / 100

ACTIONS = ["attack", "defend", "charge"]
BEATS = {("attack", "charge"), ("charge", "defend"), ("defend", "attack")}
commit = lambda seed: hashlib.sha256(seed.encode()).hexdigest()

# ---------- session helpers ----------
async def open_session(s, u: User, game: str, stake_ton: float, request_id: str, state_fn):
    if not await gs(s, f"{game}_on"): raise HTTPException(403, "game_disabled")
    lo, hi = await gs(s, f"{game}_min"), await gs(s, f"{game}_max")
    stake = int(round(stake_ton * NANO))
    if not (int(lo * NANO) <= stake <= int(hi * NANO)): raise HTTPException(400, "bad_stake")
    rate_limit(f"game:{u.id}", 40)
    await s.execute(select(User).where(User.id == u.id).with_for_update())  # serialize per user
    old = (await s.execute(select(GameSession).where(GameSession.user_id == u.id,
           GameSession.request_id == request_id))).scalar_one_or_none()
    if old: return old, False                      # idempotent replay
    op = (await s.execute(select(GameSession).where(GameSession.user_id == u.id,
          GameSession.game == game, GameSession.status == "open"))).scalars().first()
    if op: raise HTTPException(409, {"code": "already_open", "session_id": op.id})
    seed, sid = secrets.token_hex(16), uuid.uuid4().hex
    try:
        await post_tx(s, u.id, "game_loss", -stake, f"stake:{sid}", {"game": game, "session": sid})
    except ValueError:
        raise HTTPException(402, "insufficient")
    g = GameSession(id=sid, user_id=u.id, game=game, stake=stake, seed=seed,
                    state=json.dumps(state_fn(seed)), request_id=request_id)
    s.add(g); await s.flush()
    return g, True

async def get_locked(s, u: User, sid: str, game: str | None = None) -> GameSession:
    q = select(GameSession).where(GameSession.id == sid, GameSession.user_id == u.id).with_for_update()
    g = (await s.execute(q)).scalar_one_or_none()
    if not g or (game and g.game != game): raise HTTPException(404, "not_found")
    return g

async def finish(s, u: User, g: GameSession, payout: int, kind: str = "game_win"):
    """Resolve exactly once. Payout cap enforced server-side."""
    if g.status != "open": return
    payout = min(payout, int(await gs(s, "max_payout") * NANO))
    g.status, g.payout, g.resolved_at = "resolved", payout, now()
    if payout > 0:
        await post_tx(s, u.id, kind, payout, f"payout:{g.id}", {"game": g.game, "session": g.id})
        if kind == "game_win": u.total_earned = max(0, u.total_earned - min(g.stake, payout))  # leaderboard = net
    log.info("GAME user=%s %s stake=%s payout=%s", u.id, g.game, g.stake, payout)

async def view(s, u: User, g: GameSession) -> dict:
    st = json.loads(g.state)
    if g.game == "crash" and g.status == "open":   # lazy crash resolution
        growth = await gs(s, "crash_growth")
        if mult_at(time.time() - st["t0"], growth) >= st["crash"]:
            await finish(s, u, g, 0); st["result"] = "lose"; g.state = json.dumps(st); await s.commit()
    v = {"id": g.id, "game": g.game, "status": g.status, "stake": g.stake / NANO,
         "payout": g.payout / NANO, "commit": commit(g.seed), "balance": u.balance / NANO,
         "result": st.get("result")}
    if g.status == "resolved": v["seed"] = g.seed
    if g.game == "crash":
        v.update(t0_ms=int(st["t0"] * 1000), server_ms=int(time.time() * 1000), growth=await gs(s, "crash_growth"))
        if g.status == "resolved": v["crash"] = st["crash"]; v["cash"] = st.get("cash")
    elif g.game == "bomb":
        k, n, edge = len(st["picked"]), st["n"], await gs(s, "bomb_edge")
        v.update(bombs=n, picked=st["picked"], mult=bomb_mult(k, n, edge),
                 next=bomb_mult(k + 1, n, edge) if k < 25 - n else None,
                 cashout=min(g.stake * bomb_mult(k, n, edge), await gs(s, "max_payout") * NANO) / NANO)
        if g.status == "resolved": v["mines"] = st["mines"]
    elif g.game == "arena":
        v.update(rounds=st["moves"], score=st["score"])
    elif g.game == "wheel":
        v.update(idx=st.get("idx"), mult=st.get("mult"))
    return v

# ---------- router ----------
router = APIRouter(prefix="/api/games")
static_router = APIRouter()

class StakeIn(BaseModel):
    stake: float = Field(gt=0, le=1000)
    request_id: str = Field(min_length=8, max_length=64)

class BombIn(StakeIn):
    bombs: int = Field(default=3, ge=1, le=20)

class SidIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=40)

class PickIn(SidIn):
    cell: int = Field(ge=0, le=24)

class MoveIn(SidIn):
    action: str

@router.get("/config")
async def config(u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    day = now().strftime("%Y-%m-%d")
    spun = (await s.execute(select(DailySpin.id).where(DailySpin.user_id == u.id, DailySpin.day == day))).first()
    nxt = (now() + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tables = {}
    for name in ("wheel_low", "wheel_high"):
        t = await gs(s, name); tw = sum(r["weight"] for r in t)
        tables[name] = {"rows": [{"mult": r["mult"], "p": r["weight"] / tw} for r in t], "rtp": rtp(t)}
    opens = (await s.execute(select(GameSession).where(GameSession.user_id == u.id,
             GameSession.status == "open"))).scalars().all()
    games = {}
    for gname in ("daily", "crash", "arena", "bomb", "wheel"):
        games[gname] = {"on": await gs(s, f"{gname}_on")}
        if gname != "daily": games[gname].update(min=await gs(s, f"{gname}_min"), max=await gs(s, f"{gname}_max"))
    return {"games": games, "balance": u.balance / NANO, "server_ms": int(time.time() * 1000),
            "daily": {"available": not spun, "next_ms": int(nxt.timestamp() * 1000),
                      "prizes": [{"tier": p["tier"], "amount": p["amount"]} for p in await gs(s, "daily_prizes")]},
            "wheel": {**tables, "split": await gs(s, "wheel_split")},
            "bomb": {"edge": await gs(s, "bomb_edge")}, "arena": {"win_mult": await gs(s, "arena_win_mult")},
            "open": [{"id": o.id, "game": o.game} for o in opens]}

@router.post("/daily/spin")
async def daily(u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    if not await gs(s, "daily_on"): raise HTTPException(403, "game_disabled")
    rate_limit(f"daily:{u.id}", 5)
    await s.execute(select(User).where(User.id == u.id).with_for_update())
    day = now().strftime("%Y-%m-%d")
    if (await s.execute(select(DailySpin.id).where(DailySpin.user_id == u.id, DailySpin.day == day))).first():
        raise HTTPException(409, "already_spun")
    prizes = await gs(s, "daily_prizes"); seed = secrets.token_hex(16)
    i = pick(seed, "daily", [p["weight"] for p in prizes]); amt = int(prizes[i]["amount"] * NANO)
    s.add(DailySpin(user_id=u.id, day=day, tier=prizes[i]["tier"], amount=amt))
    await post_tx(s, u.id, "reward", amt, f"daily:{u.id}:{day}", {"tier": prizes[i]["tier"]})
    await s.commit()
    return {"idx": i, "tier": prizes[i]["tier"], "amount": amt / NANO, "balance": u.balance / NANO}

@router.post("/wheel/play")
async def wheel_play(b: StakeIn, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    split = await gs(s, "wheel_split")
    name = "wheel_high" if b.stake >= split else "wheel_low"
    table = await gs(s, name)
    def init(seed):
        i = pick(seed, "wheel", [r["weight"] for r in table])
        return {"table": name, "idx": i, "mult": table[i]["mult"]}
    g, new = await open_session(s, u, "wheel", b.stake, b.request_id, init)
    st = json.loads(g.state)
    if new: await finish(s, u, g, int(g.stake * st["mult"])); st["result"] = "win" if st["mult"] >= 1 else "lose"; g.state = json.dumps(st)
    await s.commit()
    return {**await view(s, u, g), "table": st["table"]}

@router.post("/crash/start")
async def crash_start(b: StakeIn, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    g, _ = await open_session(s, u, "crash", b.stake, b.request_id,
                              lambda seed: {"crash": crash_point(seed), "t0": time.time()})
    await s.commit(); return await view(s, u, g)

@router.post("/crash/cashout")
async def crash_cashout(b: SidIn, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    g = await get_locked(s, u, b.session_id, "crash")
    if g.status == "open":
        st = json.loads(g.state); growth = await gs(s, "crash_growth"); grace = await gs(s, "crash_grace_ms") / 1000
        m = mult_at(time.time() - st["t0"] - grace, growth)
        if m >= st["crash"]:
            await finish(s, u, g, 0); st["result"] = "lose"
        else:
            st["cash"], st["result"] = m, "win"; await finish(s, u, g, int(g.stake * m))
        g.state = json.dumps(st)
    await s.commit(); return await view(s, u, g)

@router.get("/crash/history")
async def crash_history(u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    rows = (await s.execute(select(GameSession).where(GameSession.game == "crash", GameSession.status == "resolved")
            .order_by(GameSession.resolved_at.desc()).limit(20))).scalars().all()
    return [json.loads(r.state)["crash"] for r in rows]

@router.post("/bomb/start")
async def bomb_start(b: BombIn, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    def init(seed):
        cells = list(range(25))
        for i in range(24, 0, -1):
            j = int(rnd(seed, f"shuf:{i}") * (i + 1)); cells[i], cells[j] = cells[j], cells[i]
        return {"n": b.bombs, "mines": sorted(cells[:b.bombs]), "picked": []}
    g, _ = await open_session(s, u, "bomb", b.stake, b.request_id, init)
    await s.commit(); return await view(s, u, g)

@router.post("/bomb/pick")
async def bomb_pick(b: PickIn, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    g = await get_locked(s, u, b.session_id, "bomb"); st = json.loads(g.state)
    if g.status != "open" or b.cell in st["picked"]: raise HTTPException(409, "invalid_move")
    edge = await gs(s, "bomb_edge")
    if b.cell in st["mines"]:
        st["picked"].append(b.cell); st["result"] = "lose"; st["hit"] = b.cell; await finish(s, u, g, 0)
    else:
        st["picked"].append(b.cell)
        if len(st["picked"]) == 25 - st["n"]:
            st["result"] = "win"; await finish(s, u, g, int(g.stake * bomb_mult(len(st["picked"]), st["n"], edge)))
    g.state = json.dumps(st); await s.commit()
    v = await view(s, u, g); v["hit"] = st.get("hit"); return v

@router.post("/bomb/cashout")
async def bomb_cashout(b: SidIn, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    g = await get_locked(s, u, b.session_id, "bomb"); st = json.loads(g.state)
    if g.status != "open" or not st["picked"]: raise HTTPException(409, "invalid_move")
    st["result"] = "win"; await finish(s, u, g, int(g.stake * bomb_mult(len(st["picked"]), st["n"], await gs(s, "bomb_edge"))))
    g.state = json.dumps(st); await s.commit(); return await view(s, u, g)

@router.post("/arena/start")
async def arena_start(b: StakeIn, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    init = lambda seed: {"opp": [ACTIONS[int(rnd(seed, f"opp:{i}") * 3)] for i in range(3)], "moves": [], "score": 0}
    g, _ = await open_session(s, u, "arena", b.stake, b.request_id, init)
    await s.commit(); return await view(s, u, g)

@router.post("/arena/move")
async def arena_move(b: MoveIn, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    if b.action not in ACTIONS: raise HTTPException(400, "bad_action")
    g = await get_locked(s, u, b.session_id, "arena"); st = json.loads(g.state)
    if g.status != "open": raise HTTPException(409, "invalid_move")
    opp = st["opp"][len(st["moves"])]
    res = "draw" if opp == b.action else "win" if (b.action, opp) in BEATS else "lose"
    st["score"] += {"win": 1, "lose": -1, "draw": 0}[res]
    st["moves"].append({"me": b.action, "opp": opp, "res": res})
    if len(st["moves"]) == 3:
        if st["score"] > 0:
            st["result"] = "win"; await finish(s, u, g, int(g.stake * await gs(s, "arena_win_mult")))
        elif st["score"] == 0:
            st["result"] = "draw"; await finish(s, u, g, g.stake, "refund")
        else:
            st["result"] = "lose"; await finish(s, u, g, 0)
    g.state = json.dumps(st); await s.commit(); return await view(s, u, g)

@router.get("/session/{sid}")
async def session_view(sid: str, u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    g = await get_locked(s, u, sid); v = await view(s, u, g); await s.commit(); return v

@router.get("/history")
async def history(u: User = Depends(current_user), s: AsyncSession = Depends(db)):
    rows = (await s.execute(select(GameSession).where(GameSession.user_id == u.id, GameSession.status == "resolved")
            .order_by(GameSession.resolved_at.desc()).limit(30))).scalars().all()
    return [{"game": r.game, "stake": r.stake / NANO, "payout": r.payout / NANO, "seed": r.seed,
             "at": r.resolved_at.isoformat()} for r in rows]

@static_router.get("/games.js")
async def games_js(): return FileResponse(os.path.join(HERE, "games.js"), media_type="application/javascript")

@static_router.get("/")
async def index_with_games():
    html = open(os.path.join(HERE, "index.html"), encoding="utf-8").read()
    return HTMLResponse(html.replace("</body>", '<script src="/games.js"></script></body>'))

# Install: drop the old "/" route from main, then mount ours (so index.html itself never needs editing).
app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/"]
app.include_router(static_router)
app.include_router(router)

# ---------- admin bot commands ----------
@dp.message(Command("games"))
async def cmd_games(m: Message):
    if not is_admin(m.from_user.id): return
    async with Session() as s:
        lines = [f"{k} = {json.dumps(await gs(s, k))}"[:300] for k in CFG]
    await m.answer("\n".join(lines))

@dp.message(Command("setgame"))
async def cmd_setgame(m: Message):
    """/setgame <key> <json>   e.g. /setgame bomb_on false   |   /setgame crash_max 5"""
    if not is_admin(m.from_user.id): return
    try:
        _, key, raw = m.text.split(maxsplit=2); val = json.loads(raw)
        if key not in CFG: return await m.answer("unknown key")
        if type(val) is not type(CFG[key]) and not (isinstance(val, (int, float)) and isinstance(CFG[key], (int, float))):
            return await m.answer("wrong type")
        if key in ("wheel_low", "wheel_high"):
            if rtp(val) > 1.0: return await m.answer(f"rejected: RTP {rtp(val):.3f} > 1")
            assert all({"mult", "weight"} <= set(r) for r in val)
        if key == "daily_prizes": assert all({"tier", "amount", "weight"} <= set(r) for r in val)
        if key.endswith(("_min", "_max")) and val <= 0: return await m.answer("must be > 0")
    except Exception:
        return await m.answer("invalid input")
    async with Session() as s:
        row = await s.get(Setting, key)
        if row: row.value = json.dumps(val)
        else: s.add(Setting(key=key, value=json.dumps(val)))
        await admin_log(s, m, f"setgame {key} {raw}"); await s.commit()
    await m.answer("done")

app = main.app  # `uvicorn games:app`
