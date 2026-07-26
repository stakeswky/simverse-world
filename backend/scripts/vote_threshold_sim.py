#!/usr/bin/env python3
"""阈值 × 分散票 交互效应离线模拟 (read-only, zero LLM, no DB writes).

Question this answers
---------------------
S2-5 的审批门开了 → civic poll 现在要过 `POLIS_POLICY_SIMPLE_MAJORITY_THRESHOLD`
(线上 0.50) 才执行;而 NPC 投票修复恰好让票**变分散**了。生产实测那一组是
8/14 = 57.1%,勉强过线。那么:**选项数 K 变化时,过线概率是多少?**

Method
------
直接 import 生产的 `civic_service._npc_choice`(不是复写),用 stub 的 db /
relation_service 跑纯打分路径。对每个 (K, poll 形态) 组合生成大量随机 poll,
每张 poll 让整个 cohort 投一遍,统计 top-share ≥ 阈值的比例。

Cohort
------
- `--residents FILE.json`: 真实 dump(见 --help 里的 vm212 只读一行命令)。
- 缺省: 合成 cohort,A2 边际锁死为生产实测的 M10/L3/H1,其余维度按
  `--homogeneity` 采样(1.0 = 全 M/全同,0.0 = 均匀分布)。因为其余维度的
  真实联合分布未知,所以对 homogeneity 做敏感性扫描而不是拍一个数。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import statistics
import sys
from collections import Counter

import os  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.services import civic_service as cs  # noqa: E402  (real production scorer)

assert not cs.settings.civic_npc_choice_legacy, (
    "CIVIC_NPC_CHOICE_LEGACY=true — 本模拟要评估的是修复后的打分器，"
    "请在没有该 env 的环境里跑（或临时 unset）。"
)

DIMS = ("A1", "A2", "So1", "Ac1", "E1")
PROD_A2 = ["M"] * 10 + ["L"] * 3 + ["H"] * 1  # ops-audit 实测 14 个 NPC


# ── stubs ────────────────────────────────────────────────────────────────
class R:
    def __init__(self, i, slug, dims, duty=None):
        self.id, self.slug = i, slug
        self.meta_json = {"sbti": {"dimensions": dims}, "duty": {"key": duty}}


class P:
    def __init__(self, q):
        self.question, self.id = q, q


class _Pair:
    def __init__(self, a):
        self.affinity = a


class RelStub:
    """get_pair 返回一个采样的 affinity;None = 互不相识(生产多数情况)."""

    def __init__(self, rng, p_known=0.35, lo=-0.3, hi=0.6):
        self.rng, self.p_known, self.lo, self.hi = rng, p_known, lo, hi

    async def get_pair(self, db, a, b):
        if self.rng.random() > self.p_known:
            return None
        return _Pair(self.rng.uniform(self.lo, self.hi))


# ── cohort ───────────────────────────────────────────────────────────────
def make_cohort(rng, n=14, homogeneity=0.6):
    """A2 锁生产实测边际;其余维度按 homogeneity 采样(越高越多 M = 越无信号)."""
    a2 = PROD_A2[:n] if n <= len(PROD_A2) else PROD_A2 + ["M"] * (n - len(PROD_A2))
    rng.shuffle(a2)
    out = []
    for i in range(n):
        dims = {"A2": a2[i]}
        for d in ("A1", "So1", "Ac1", "E1"):
            dims[d] = "M" if rng.random() < homogeneity else rng.choice(["H", "L"])
        duty = rng.choice([None, None, None, "shop_keeper", "tavern_hub"])
        out.append(R(i + 1, f"npc{i+1:02d}", dims, duty))
    return out


def load_cohort(path):
    raw = json.load(open(path))
    return [
        R(i + 1, r.get("slug", f"npc{i}"), r.get("dimensions") or r.get("dims") or {},
          r.get("duty"))
        for i, r in enumerate(raw)
    ]


# ── poll shapes ──────────────────────────────────────────────────────────
TOPICS = [
    ("policy", "税率 tax 财政 treasury 调整"),
    ("policy", "集市 market 价格 price 规则"),
    ("system_config", "酒馆 tavern 社交 聚会 时段"),
    ("dynamic_location", "兴建 一座 学堂 工程"),
    ("narrative", "文化 展 讲 书 活动"),
    ("system_config", "制度 条例 秩序 章程 调整"),
]


def make_options(rng, k, shape):
    """三种真实形态。shape='policy_amend' 是 S2-5 政策修订的样子(全带 effect、
    全 reversible),也是最容易分散的一种。"""
    opts = []
    if shape == "status_quo_plus":
        opts.append({"label": "维持现状", "effect": None})
        pool = rng.sample(TOPICS, min(k - 1, len(TOPICS)))
        for j in range(k - 1):
            t, blob = pool[j % len(pool)]
            opts.append({"label": f"方案{j+1} {blob}", "effect": {"type": t, "key": f"k{j}", "note": blob}})
    elif shape == "policy_amend":
        t, blob = rng.choice(TOPICS[:2])
        for j in range(k):
            opts.append({"label": f"调到 {rng.randint(1,40)}% ({blob})",
                         "effect": {"type": "policy", "key": f"pol_{rng.randint(0,999)}",
                                    "value": rng.random(), "note": blob}})
    else:  # mixed_topics
        pool = rng.sample(TOPICS, min(k, len(TOPICS)))
        for j in range(k):
            t, blob = pool[j % len(pool)]
            opts.append({"label": f"选项{j+1} {blob}", "effect": {"type": t, "key": f"k{j}", "note": blob}})
    rng.shuffle(opts)
    return opts


def norm_entropy(tally):
    n = sum(tally)
    k = len(tally)
    if n == 0 or k < 2:
        return 0.0
    h = -sum((c / n) * math.log(c / n) for c in tally if c)
    return h / math.log(k)


# ── one poll ─────────────────────────────────────────────────────────────
async def run_poll(cohort, opts, rng, proposer=True):
    if proposer and opts:
        opts[0]["_proposer_slug"] = rng.choice(cohort).slug
    by_slug = {r.slug: r for r in cohort}
    rel = RelStub(rng)
    tally = [0] * len(opts)
    poll = P(f"关于{rng.randint(0,10**9)}的镇务议案")
    for r in cohort:
        i = await cs._npc_choice(None, r, poll, opts, rel, by_slug)
        tally[i] += 1
    return tally


async def sweep(cohort_fn, shapes, ks, trials, thresholds, seed=20260725):
    rows = []
    for shape in shapes:
        for k in ks:
            shares, ents, tallies = [], [], []
            for t in range(trials):
                rng = random.Random(f"{seed}|{shape}|{k}|{t}")
                cohort = cohort_fn(rng)
                opts = make_options(rng, k, shape)
                tal = await run_poll(cohort, opts, rng)
                n = sum(tal)
                shares.append(max(tal) / n)
                ents.append(norm_entropy(tal))
                tallies.append(tuple(sorted(tal, reverse=True)))
            rows.append({
                "shape": shape, "k": k,
                "share_mean": statistics.mean(shares),
                "share_p10": sorted(shares)[int(0.10 * len(shares))],
                "share_med": statistics.median(shares),
                "entropy": statistics.mean(ents),
                "pass": {th: sum(s >= th for s in shares) / len(shares) for th in thresholds},
                "modal": Counter(tallies).most_common(3),
            })
    return rows


def main():
    ap = argparse.ArgumentParser(
        epilog="vm212 只读 dump 一行命令:\n"
               "  docker compose exec -T api python -c \"import asyncio,json;"
               "from app.db import async_session;from sqlalchemy import select;"
               "from app.models.resident import Resident;\\\n"
               "async def m():\\\n"
               " async with async_session() as d:\\\n"
               "  rs=(await d.execute(select(Resident))).scalars().all();\\\n"
               "  print(json.dumps([{'slug':r.slug,'dimensions':(r.meta_json or {}).get('sbti',{}).get('dimensions',{}),"
               "'duty':(r.meta_json or {}).get('duty',{}).get('key')} for r in rs],ensure_ascii=False))\\\n"
               "asyncio.run(m())\" > /tmp/residents.json",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--residents")
    ap.add_argument("--n", type=int, default=14)
    ap.add_argument("--trials", type=int, default=2000)
    ap.add_argument("--homogeneity", type=float, default=0.6)
    a = ap.parse_args()

    if a.residents:
        fixed = load_cohort(a.residents)
        cohort_fn = lambda rng: fixed  # noqa: E731
        label = f"real dump n={len(fixed)}"
    else:
        cohort_fn = lambda rng: make_cohort(rng, a.n, a.homogeneity)  # noqa: E731
        label = f"synthetic n={a.n} homogeneity={a.homogeneity} (A2 边际 = 生产实测 M10/L3/H1)"

    ths = [0.40, 0.45, 0.50, 0.667]
    rows = asyncio.run(sweep(cohort_fn, ["status_quo_plus", "policy_amend", "mixed_topics"],
                             [2, 3, 4, 5], a.trials, ths))
    print(f"# cohort: {label}   trials/cell={a.trials}\n")
    hdr = f"{'poll 形态':<18}{'K':>2} {'首位得票率均值':>10} {'中位':>7} {'p10':>7} {'归一熵':>7}" \
          + "".join(f"{'过'+str(int(t*1000)/10)+'%':>9}" for t in ths)
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['shape']:<18}{r['k']:>2} {r['share_mean']:>13.1%} {r['share_med']:>7.1%} "
              f"{r['share_p10']:>7.1%} {r['entropy']:>7.3f}"
              + "".join(f"{r['pass'][t]:>9.1%}" for t in ths))
    print("\n# 最常见票型 (降序 tally)")
    for r in rows:
        print(f"  {r['shape']:<18}K={r['k']}  " +
              "  ".join(f"{list(t)}×{c}" for t, c in r["modal"]))


if __name__ == "__main__":
    main()
