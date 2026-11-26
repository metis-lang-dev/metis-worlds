package semworld

// Taste: what the person likes, as beliefs of the semantic world (nina-live, 2026-11-24; the user:
// "register the semantic entities, arrange them in preferences, mark them with free tagging, and do
// the select operation on them, general, so the lifted Metis rules apply in any domain").
//
// An Item is anything a domain can offer: a radio station, a light's colour, a scene, a recipe. It
// has a kind and free tags (a genre, a mood, the person's own words once they kept what the words
// found). A preference is the belief that the person wants the item in a context (the time of day,
// a mood), kept as log-odds: kept is evidence for, skipped against, and evidence fades with a
// half-life, so an old taste gives way. The home's character is a prior per tag and context: what
// the home leans to before it knows the person, and still where the person has no opinion.
//
// Select is the semantic map's select (bind a role to the likeliest entity), over taste: the item
// of a kind that matches the tags best and is liked most now; when that is still unsure, an item
// tried least (the home's curiosity, deterministic: a function of the state, so a replay agrees).
// Everything that changes taste is an event of the world (Register, Tag, Prefer, Prior); Select
// and Score only read.

import (
	"fmt"
	"math"
	"sort"
	"strings"
)

// Item is a thing a domain can offer.
type Item struct {
	ID   string   `json:"id"`
	Kind string   `json:"kind"` // station, colour, scene, ...
	Name string   `json:"name"`
	Ref  string   `json:"ref,omitempty"` // the domain's own reference (a station's URL, a light's colour command)
	Tags []string `json:"tags,omitempty"`
}

// Context is when a preference holds: the time of day and the mood ("" any).
type Context struct {
	Part string `json:"part,omitempty"` // morning, afternoon, evening, night
	Mood string `json:"mood,omitempty"` // calm, cozy, focus, lively, sleep, wake
}

// ckey is a context key and its weight in a score.
type ckey struct {
	k string
	w float64
}

// keys are the context's keys, most specific first, with their weights in a score.
func (c Context) keys() []ckey {
	var out []ckey
	if c.Part != "" && c.Mood != "" {
		out = append(out, ckey{"part:" + c.Part + "+mood:" + c.Mood, 1})
	}
	if c.Mood != "" {
		out = append(out, ckey{"mood:" + c.Mood, 0.7})
	}
	if c.Part != "" {
		out = append(out, ckey{"part:" + c.Part, 0.6})
	}
	return append(out, ckey{"*", 0.3})
}

// Pref is the evidence for one item in one context.
type Pref struct {
	L  float64 `json:"l"`  // log-odds of wanted, from the evidence (decaying from At)
	N  int     `json:"n"`  // pieces of evidence
	At float64 `json:"at"` // the last evidence
}

// Taste is the world's taste.
type Taste struct {
	Items    map[string]*Item   `json:"items"`
	Prefs    map[string]*Pref   `json:"prefs"`  // item|context-key
	Priors   map[string]float64 `json:"priors"` // tag|context-key: the character's lean, log-odds
	HalfLife float64            `json:"half_life"`
	Curious  float64            `json:"curious"` // how often the home tries something new on purpose (0..1)
}

// NewTaste is an empty taste (half-life 30 days; curious one time in seven).
func NewTaste() *Taste {
	return &Taste{Items: map[string]*Item{}, Prefs: map[string]*Pref{}, Priors: map[string]float64{},
		HalfLife: 30 * 86400, Curious: 1.0 / 7}
}

func norm(s string) string { return strings.Join(strings.Fields(strings.ToLower(s)), " ") }

// Register enters an item, or renews its name and adds its tags.
func (t *Taste) Register(it Item) {
	if it.ID == "" {
		return
	}
	old, ok := t.Items[it.ID]
	if !ok {
		c := it
		c.Tags = nil
		old = &c
		t.Items[it.ID] = old
	}
	if it.Name != "" {
		old.Name = it.Name
	}
	if it.Kind != "" {
		old.Kind = it.Kind
	}
	if it.Ref != "" {
		old.Ref = it.Ref
	}
	t.Tag(it.ID, it.Tags...)
}

// Tag adds free tags to an item (the person's words: each word is a tag, and the words together).
func (t *Taste) Tag(id string, tags ...string) {
	it, ok := t.Items[id]
	if !ok {
		return
	}
	have := map[string]bool{}
	for _, x := range it.Tags {
		have[x] = true
	}
	for _, tag := range tags {
		tag = norm(tag)
		if tag == "" {
			continue
		}
		for _, x := range append([]string{tag}, strings.Fields(tag)...) {
			if !have[x] && (len(x) > 2 || x == tag) {
				have[x] = true
				it.Tags = append(it.Tags, x)
			}
		}
	}
	sort.Strings(it.Tags)
}

// decayed is the evidence's log-odds at now.
func (t *Taste) decayed(p *Pref, now float64) float64 {
	if p == nil {
		return 0
	}
	if t.HalfLife <= 0 || now <= p.At {
		return p.L
	}
	return p.L * math.Pow(0.5, (now-p.At)/t.HalfLife)
}

// Prefer is evidence about an item in a context: delta in log-odds (kept +1, skipped -1, a person's
// "I love this" +2); it lands on every key of the context.
func (t *Taste) Prefer(id string, c Context, delta, now float64) {
	if _, ok := t.Items[id]; !ok {
		return
	}
	for _, k := range c.keys() {
		key := id + "|" + k.k
		p := t.Prefs[key]
		if p == nil {
			p = &Pref{}
			t.Prefs[key] = p
		}
		p.L = t.decayed(p, now) + delta
		p.N++
		p.At = now
	}
}

// Prior is the character's lean for a tag in a context ("" part and mood: always).
func (t *Taste) Prior(tag string, c Context, l float64) {
	ks := c.keys()
	t.Priors[norm(tag)+"|"+ks[0].k] = l
}

// Score is P(the person wants the item now) and how much evidence there is.
func (t *Taste) Score(id string, c Context, now float64) (float64, int) {
	it, ok := t.Items[id]
	if !ok {
		return 0, 0
	}
	l, n := 0.0, 0
	for _, k := range c.keys() {
		if p := t.Prefs[id+"|"+k.k]; p != nil {
			l += k.w * t.decayed(p, now)
			if k.k == "*" {
				n = p.N
			}
		}
		for _, tag := range it.Tags {
			l += k.w * t.Priors[tag+"|"+k.k]
		}
	}
	return 1 / (1 + math.Exp(-l)), n
}

// Choice is what Select chose.
type Choice struct {
	ID       string  `json:"id"`
	P        float64 `json:"p"`        // the belief the person wants it now
	Match    float64 `json:"match"`    // the share of the tags asked for that it carries
	Explored bool    `json:"explored"` // chosen to try something, not because it is liked
}

// matches is the share of TAGS the item carries (its tags, its name's words, its kind).
func (it *Item) matches(tags []string) float64 {
	if len(tags) == 0 {
		return 1
	}
	have := map[string]bool{norm(it.Kind): true}
	for _, x := range it.Tags {
		have[x] = true
	}
	for _, w := range strings.Fields(norm(it.Name)) {
		have[w] = true
	}
	n, m := 0, 0
	for _, tag := range tags {
		for _, w := range strings.Fields(norm(tag)) {
			if len(w) < 3 {
				continue
			}
			n++
			if have[w] {
				m++
				continue
			}
			for h := range have { // a stem: "relaxing" finds "relax"
				if len(h) >= 4 && len(w) >= 4 && h[:4] == w[:4] {
					m++
					break
				}
			}
		}
	}
	if n == 0 {
		return 1
	}
	return float64(m) / float64(n)
}

// Select is the item of KIND that matches TAGS best (half of them at least) and is liked most in
// the context, EXCLUDE left out. When the best is still unsure (P below 0.6 with little evidence),
// or one time in 1/Curious of the matching evidence, it is an item tried least instead: the home's
// curiosity. ok false: nothing of that kind matches.
func (t *Taste) Select(kind string, tags []string, c Context, exclude []string, now float64) (Choice, bool) {
	ex := map[string]bool{}
	for _, x := range exclude {
		ex[x] = true
	}
	type cand struct {
		Choice
		n int
	}
	var cs []cand
	best := 0.0
	for id, it := range t.Items {
		if ex[id] || (kind != "" && it.Kind != kind) {
			continue
		}
		m := it.matches(tags)
		if m < 0.5 {
			continue
		}
		p, n := t.Score(id, c, now)
		cs = append(cs, cand{Choice{ID: id, P: p, Match: m}, n})
		best = math.Max(best, m)
	}
	var keep []cand
	evidence := 0
	for _, x := range cs {
		if x.Match == best {
			keep = append(keep, x)
			evidence += x.n
		}
	}
	if len(keep) == 0 {
		return Choice{}, false
	}
	sort.Slice(keep, func(i, j int) bool {
		if keep[i].P != keep[j].P {
			return keep[i].P > keep[j].P
		}
		return keep[i].ID < keep[j].ID
	})
	top := keep[0]
	curious := t.Curious > 0 && len(keep) > 1 && evidence > 0 && evidence%int(math.Round(1/t.Curious)) == 0
	if (top.P < 0.6 && top.n < 3) || curious {
		least := keep[0]
		for _, x := range keep[1:] {
			if x.n < least.n || (x.n == least.n && x.ID < least.ID) {
				least = x
			}
		}
		if least.ID != top.ID || top.P < 0.6 {
			least.Explored = true
			return least.Choice, true
		}
	}
	return top.Choice, true
}

// hashText is the taste in a sorted text walk (the world's checkpoint).
func (t *Taste) hashText() string {
	if t == nil {
		return ""
	}
	var b strings.Builder
	for _, id := range sortedMapKeys(t.Items) {
		it := t.Items[id]
		fmt.Fprintf(&b, "I %s %s %s %s %v\n", id, it.Kind, it.Name, it.Ref, it.Tags)
	}
	for _, k := range sortedMapKeys(t.Prefs) {
		fmt.Fprintf(&b, "P %s %v\n", k, *t.Prefs[k])
	}
	for _, k := range sortedMapKeys(t.Priors) {
		fmt.Fprintf(&b, "R %s %v\n", k, t.Priors[k])
	}
	fmt.Fprintf(&b, "H %v %v\n", t.HalfLife, t.Curious)
	return b.String()
}

func sortedMapKeys[V any](m map[string]V) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// Get is an item (a copy).
func (t *Taste) Get(id string) (Item, bool) {
	it, ok := t.Items[id]
	if !ok {
		return Item{}, false
	}
	c := *it
	c.Tags = append([]string(nil), it.Tags...)
	return c, true
}

// HashText is the taste's part of a world's checkpoint.
func (t *Taste) HashText() string { return t.hashText() }
