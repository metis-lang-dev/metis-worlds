"""hier_cards.py — the specialists' cards on E2B (alf-hierarchy step 2): each card alone (its prompt, spoken
examples and grammar, as metis_agent.intent_check serves one domain) and the five as one union
(the orchestrator's intent_turn + intent_grammar, as it serves several domains), every corpus
row; a row is right when its verb is AND its mapped atom is the corpus's expected goal atom.

    cd metis-agent/py && PYTHONPATH=$PWD .venv/bin/python …/experiments/hier_cards.py DOMAINS_ROOT CORPORA_DIR OUT_PREFIX [alone|union|both]

Runs under metis-agent's venv (the orchestrator's intent_turn/intent_grammar, the mapper, the
model). DOMAINS_ROOT/<spec>/{<spec>.llp, intent.yaml, domain.yaml}: the reference game's
person-mode packages (gen_hier.generate(…, [], [], intents=True)) with ../hier/ the bases;
CORPORA_DIR: domains/hier (<spec>/<spec>-corpus.tsv). The union's expectations: a row's own
card's verb and atom, else the corpus's union column (alternatives, the first the strict one),
else UNKNOWN. Writes OUT_PREFIX-<spec>.jsonl, -union.jsonl, -summary.json."""
import json
import os
import sys
import time
from pathlib import Path

import yaml
from metis_agent.intent_check import GGUF, declared, generator, in_program, mapped
from metis_agent.intent_domain import build
from metis_agent.llm import LLM
from metis_agent.mapper import Mapper
from metis_agent.orchestrator import IntentDomain, intent_grammar, intent_turn

root, corpora, prefix = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
mode = sys.argv[4] if len(sys.argv) > 4 else "both"
NAMES = ("nav", "access", "grasp", "place", "task")
gen = generator(root)
specs = {n: gen.load_from(root / n) for n in NAMES}
maps = {n: (Mapper(build(n, root=root)["CARD"]), declared(build(n, root=root))) for n in NAMES}


def rows(n):
    out = []
    for line in (corpora / n / ("%s-corpus.tsv" % n)).read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            f = line.split("\t")
            alts = [tuple(a.strip().split("/", 2)) for a in f[4].split("|")] if len(f) > 4 and f[4].strip() else []
            out.append({"utt": f[0], "want": f[1], "atom_want": f[3] if len(f) > 3 and f[3] else None, "corpus": n,
                        "union": alts})
    return out


ROWS = {n: rows(n) for n in NAMES}


def norm(a):
    return a.replace(" ", "") if a else a


def answer(llm, persona, utt, gbnf):
    t0 = time.perf_counter()
    res = llm.two_pass(persona, utt, gbnf)
    try:
        j = json.loads(res["json"])
    except ValueError:
        j = {}
    return j, res, round((time.perf_counter() - t0) * 1e3)


def load_llm(persona):
    llm = LLM(os.environ.get("E2B_GGUF") or str(GGUF), n_ctx=8192, n_batch=512, n_threads=4, n_gpu_layers=99)
    llm.prime(persona)
    return llm


summary = {}
if mode in ("alone", "both"):
    for n in NAMES:
        persona, gbnf = gen.prompt(specs[n]) + gen.spoken(specs[n]), gen.grammar(specs[n])
        llm = load_llm(persona)
        recs = []
        for r in ROWS[n]:
            j, res, ms = answer(llm, persona, r["utt"], gbnf)
            verb = j.get("intent", "")
            atom, err = in_program(*mapped(maps[n][0], json.dumps(j)), maps[n][1])
            verb_ok = verb == r["want"] and err is None
            atom_ok = verb_ok and (r["want"] == "UNKNOWN" or norm(atom) == norm(r["atom_want"]))
            recs.append(dict(r, got=verb, json=res["json"], voice=res["voice"], atom=atom, error=err,
                             verb_ok=verb_ok, ok=atom_ok, ms=ms))
            print("%s %s %-46r want %-7s %-26s got %s" % (n, "ok  " if atom_ok else ("VERB" if verb_ok else "MISS"), r["utt"],
                                                         r["want"], r["atom_want"] or "", res["json"]), flush=True)
        llm.close()
        with open("%s-%s.jsonl" % (prefix, n), "w") as f:
            for x in recs:
                f.write(json.dumps(x) + "\n")
        summary[n] = {"rows": len(recs), "verb": sum(x["verb_ok"] for x in recs), "atom": sum(x["ok"] for x in recs)}
        print("%s alone: verbs %d/%d, verbs+atoms %d/%d" % (n, summary[n]["verb"], len(recs), summary[n]["atom"], len(recs)), flush=True)

if mode in ("union", "both"):
    disp = {n: yaml.safe_load((root / n / "domain.yaml").read_text()).get("display", n) for n in NAMES}
    ds = [IntentDomain(n, disp[n], gen.prompt(specs[n]), gen.grammar(specs[n]), specs[n].get("asks") or ()) for n in NAMES]
    persona = intent_turn(ds) + "".join(gen.spoken(specs[n]) for n in NAMES[:1])
    gbnf = intent_grammar(ds)
    llm = load_llm(persona)
    recs = []
    for n in NAMES:
        for r in ROWS[n]:
            # the expectations, the strict one first: the row's own card, else the corpus's union column, else UNKNOWN
            alts = r["union"] or ([(n, r["want"], r["atom_want"])] if r["want"] != "UNKNOWN" else [("", "UNKNOWN", None)])
            j, res, ms = answer(llm, persona, r["utt"], gbnf)
            dom, verb = j.pop("domain", ""), j.get("intent", "")
            atom, err = (None, "no such domain")
            if dom in maps:
                atom, err = in_program(*mapped(maps[dom][0], json.dumps(j)), maps[dom][1])

            def hit(w):
                if w[1] == "UNKNOWN":
                    return verb == "UNKNOWN", verb == "UNKNOWN"
                v = (dom, verb) == w[:2] and err is None
                return v, v and norm(atom) == norm(w[2])
            hits = [hit(w) for w in alts]
            verb_ok, ok = hits[0]
            lenient = any(h[1] for h in hits)
            recs.append(dict(r, want_union=[list(w) for w in alts], got=[dom, verb], json=res["json"], atom=atom,
                             error=err, verb_ok=verb_ok, ok=ok, lenient=lenient, ms=ms))
            print("union %s %-46r want %-40s got %s/%s %s" % ("ok  " if ok else "alt " if lenient else ("VERB" if verb_ok else "MISS"),
                                                           r["utt"], " | ".join("/".join(x for x in w if x) for w in alts),
                                                           dom, verb, atom or err), flush=True)
    llm.close()
    with open("%s-union.jsonl" % prefix, "w") as f:
        for x in recs:
            f.write(json.dumps(x) + "\n")
    u = summary["union"] = {"rows": len(recs), "verb": sum(x["verb_ok"] for x in recs), "strict": sum(x["ok"] for x in recs),
                            "lenient": sum(x["lenient"] for x in recs),
                            "ambiguous_rows": sum(len(x["want_union"]) > 1 for x in recs)}
    print("union: domain+verb %d/%d; +atom strict %d/%d (%.3f, miss rate %.3f); either reading of the %d ambiguous rows %d/%d (%.3f)" % (
        u["verb"], u["rows"], u["strict"], u["rows"], u["strict"] / u["rows"], 1 - u["strict"] / u["rows"],
        u["ambiguous_rows"], u["lenient"], u["rows"], u["lenient"] / u["rows"]), flush=True)
json.dump(summary, open("%s-summary.json" % prefix, "w"), indent=1)
print(json.dumps(summary))
