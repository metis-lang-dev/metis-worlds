package home

import (
	sw "github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/semworld"
)

// ── the assistant herself: the strain on what she thinks and hears with ──
//
// The services she runs on fail in ways that say something about her, not about a bug: a model in
// high demand (busy), a quota spent for the day (tired), no network (offline). Nina's host turns
// each such API error into a strain event (2026-11-25, the user: not to ignore it as a word
// signal; a proposition linked to Nina, on the quantized port; the subdomains interpret it later).
// Every source (the task model, the voice, the ears, the web search) is a categorical on the entry
// "nina", resting on well; an error is evidence for its kind, a success after one for well, and the
// belief forgets back to well (busy and offline in minutes, tired in hours). The entry is made at
// the first strain, so a log without one replays to the same world as before.

// Self is the assistant's own entry.
const Self = "nina"

// Strains are a source's states.
var Strains = []string{"well", "busy", "tired", "offline"}

var strainRest = sw.Belief{"well": 0.97, "busy": 0.01, "tired": 0.01, "offline": 0.01}

// strain half-lives (s): how fast a belief in the kind forgets back to well.
var strainHalf = map[string]float64{"busy": 300, "offline": 300, "tired": 3 * 3600, "well": 300}

// strainR is an error's reliability as evidence: one is a hint (unsure), two in a row likely,
// three sure (the quantized port passes each level once).
const strainR = 0.8

// wellR is a success's reliability as evidence of well: stronger (a sure strain is likely after one).
const wellR = 0.95

var strainWords = map[string]string{
	"well":    "well",
	"busy":    "busy: the service is in high demand",
	"tired":   "tired: today's quota is spent",
	"offline": "offline: the service cannot be reached",
}

// Strain folds one strain event in: source's state is KIND (well after a success), REF what
// said so (an error's gist).
func (h *Home) Strain(source, kind, ref string, now float64) error {
	h.W.Lock()
	defer h.W.Unlock()
	ok := false
	for _, k := range Strains {
		ok = ok || k == kind
	}
	if !ok || source == "" {
		return errStrain(source, kind)
	}
	w := h.W
	if w.Entries[Self] == nil {
		w.Add(&sw.Entry{ID: Self, Kind: sw.KAgent, Name: "Nina"})
	}
	if w.Var(Self, source) == nil {
		w.Declare(Self, source, sw.VCat, Strains, strainRest)
	}
	r := strainR
	if kind == "well" { // an answer proves the service works now; an error may be a fluke
		r = wellR
	}
	w.ObserveCat(Self, source, kind, r, 0, sw.Source{Kind: "self", Who: source, Ref: ref}, now)
	return nil
}

type strainErr struct{ source, kind string }

func (e strainErr) Error() string {
	return "home: strain " + e.source + " " + e.kind + " (well, busy, tired, offline)"
}

func errStrain(s, k string) error { return strainErr{s, k} }

// selfTick: each source forgets back to well, at its likeliest kind's half-life. Holds the lock.
func (h *Home) selfTick(dt float64) {
	e := h.W.Entries[Self]
	if e == nil {
		return
	}
	for _, name := range keys(e.Vars) {
		v := e.Vars[name]
		top, _ := v.Top()
		v.Cat = sw.Relax(strainRest, strainHalf[top])(v.Cat, dt)
	}
}

func (h *Home) selfPhrase(e *sw.Entry, name string) (sw.Phrase, bool) {
	subject := map[string]string{"mind": "Nina's task model", "voice": "Nina's voice model",
		"ears": "Nina's transcriber", "search": "Nina's web search"}[name]
	if subject == "" {
		subject = "Nina's " + name
	}
	return sw.Phrase{Subject: subject, Words: strainWords}, true
}

// selfPort: strain(S, K), the probability that source S is in state K (busy, tired, offline): a
// categorical over K, for the domains that will read it.
func (h *Home) selfPort() {
	w := h.W
	h.B.Offer(&sw.Port{Name: "strain", One: "K", Keys: func() [][]string {
		e := w.Entries[Self]
		if e == nil {
			return nil
		}
		var out [][]string
		for _, s := range keys(e.Vars) {
			for _, k := range Strains[1:] {
				out = append(out, []string{s, k})
			}
		}
		return out
	}, Src: func(a []string) sw.Source {
		if v := w.Var(Self, a[0]); v != nil {
			return v.Src
		}
		return sw.Source{}
	}, P: func(a []string) (float64, bool) {
		v := w.Var(Self, a[0])
		if v == nil {
			return 0, false
		}
		return v.P(a[1]), v.Src.Kind != "prior"
	}})
}
