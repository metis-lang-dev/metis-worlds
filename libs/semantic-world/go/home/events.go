package home

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"

	sw "github.com/metis-lang-dev/metis-worlds/libs/semantic-world/go/semworld"
)

// The world as a fold over events: Nina's event log keeps these, in order, and the world is
// rebuilt by applying them again. They are the world's whole input alphabet; nothing else may
// change it. Every one carries its world time At, the `now` each call takes, so the world never
// reads a clock.
//
//	ha_state   HA             Ingest
//	feed_down                 FeedDown
//	command    ID Var Value   Command (the host's prediction, written before the device call)
//	report     Person ID Var Value Ref   World.Report (a person's word)
//	conclude   Member Fact On Rule       World.Conclude (a Metis member's fact)
//	strain     ID Value Ref              Strain (the assistant's own service, ID, is VALUE: well | busy |
//	                                     tired | offline; an API error's kind, Ref its gist)
//	settle                    Settle, then every member's beat: Wake and Lines, in sorted order
//	item       Item           Taste.Register (an item a domain offers, with its tags; again: more tags)
//	prefer     ID Pref Delta  Taste.Prefer (evidence: kept +1, skipped -1, in a context)
//	prior      Value Pref Delta  Taste.Prior (the character's lean for a tag, Value, in a context)
//	curious    Delta          Taste.Curious (how often the home tries something new on purpose)
//	schedule   Sched          Schedule.Set (a member's entry: one-shot, or periodic by a cron spec or a period)
//	unschedule Member ID      Schedule.Cancel (the member's entry for its slot ID)
//
// Reading the board changes it (Lines retracts the previous level atoms, Wake records what a
// member has seen), so a beat's reads are part of applying the settle and come back in Out: a
// host must take its members' lines from there and never call Board.Lines or Board.Wake itself.
type Event struct {
	At     float64  `json:"at"`
	Kind   string   `json:"kind"`
	HA     *HAState `json:"ha,omitempty"`
	ID     string   `json:"id,omitempty"`
	Var    string   `json:"var,omitempty"`
	Value  string   `json:"value,omitempty"`
	Person string   `json:"person,omitempty"`
	Ref    string   `json:"ref,omitempty"`
	Member string   `json:"member,omitempty"`
	Fact   string   `json:"fact,omitempty"`
	On     bool     `json:"on,omitempty"`
	Rule   string   `json:"rule,omitempty"`
	// taste
	Item  *sw.Item    `json:"item,omitempty"`
	Pref  *sw.Context `json:"pref,omitempty"`
	Delta float64     `json:"delta,omitempty"`
	// the schedule
	Sched *sw.Sched `json:"sched,omitempty"`
}

// Out is what applying an event produced: outputs, recomputed by a replay, never read back.
type Out struct {
	Surprises []sw.Surprise       // the surprises this event raised
	Wake      map[string]bool     // settle: the members that beat
	Lines     map[string][]string // settle: each member's do-lines (one level atom per known key)
	Projected []sw.Line           // settle: the world's lines for the LLMs
	Due       []sw.Sched          // settle: the schedule's entries that fell due, each to its owner once
}

// Apply folds one event into the world.
func (h *Home) Apply(ev Event) (Out, error) {
	n := len(h.W.Surprises)
	var out Out
	switch ev.Kind {
	case "ha_state":
		if ev.HA == nil {
			return out, fmt.Errorf("home: ha_state without a state")
		}
		h.Ingest(*ev.HA, ev.At)
	case "item":
		if ev.Item == nil {
			return out, fmt.Errorf("home: item without an item")
		}
		h.W.Lock()
		h.W.Taste.Register(*ev.Item)
		h.W.Unlock()
	case "curious":
		h.W.Lock()
		h.W.Taste.Curious = ev.Delta
		h.W.Unlock()
	case "prefer", "prior":
		c := sw.Context{}
		if ev.Pref != nil {
			c = *ev.Pref
		}
		h.W.Lock()
		if ev.Kind == "prefer" {
			h.W.Taste.Prefer(ev.ID, c, ev.Delta, ev.At)
		} else {
			h.W.Taste.Prior(ev.Value, c, ev.Delta)
		}
		h.W.Unlock()
	case "schedule":
		if ev.Sched == nil {
			return out, fmt.Errorf("home: schedule without an entry")
		}
		h.W.Lock()
		err := h.W.Sched.Set(*ev.Sched, ev.At)
		h.W.Unlock()
		if err != nil {
			return out, err
		}
	case "unschedule":
		h.W.Lock()
		h.W.Sched.Cancel(ev.Member, ev.ID)
		h.W.Unlock()
	case "feed_down":
		h.FeedDown(ev.At)
	case "command":
		if err := h.Command(ev.ID, ev.Var, ev.Value, ev.At); err != nil {
			return out, err
		}
	case "report":
		h.W.Lock()
		_, err := h.W.Report(ev.Person, ev.ID, ev.Var, ev.Value, 0, ev.Ref, ev.At)
		h.W.Unlock()
		if err != nil {
			return out, err
		}
	case "strain":
		if err := h.Strain(ev.ID, ev.Value, ev.Ref, ev.At); err != nil {
			return out, err
		}
	case "set": // a Metis member's conclusion about the home (its mode, its mood): outright, never on a sensed variable
		if !Settable[ev.ID+"."+ev.Var] {
			return out, fmt.Errorf("home: %s.%s is not a variable a set writes", ev.ID, ev.Var)
		}
		h.W.Lock()
		v := h.W.Var(ev.ID, ev.Var)
		known := false
		for _, x := range v.Values {
			known = known || x == ev.Value
		}
		if !known {
			h.W.Unlock()
			return out, fmt.Errorf("home: %s.%s has no value %q", ev.ID, ev.Var, ev.Value)
		}
		h.W.SetCat(ev.ID, ev.Var, sw.Belief{ev.Value: 1}, sw.Source{Kind: "metis", Who: ev.Member, Ref: ev.Rule}, ev.At)
		h.W.Unlock()
	case "conclude":
		h.W.Lock()
		h.W.Conclude(ev.Member, ev.Fact, ev.On, ev.Rule, ev.At)
		h.W.Unlock()
	case "settle":
		h.Settle(ev.At)
		h.W.Lock()
		out.Due = h.due
		h.due = nil
		out.Wake, out.Lines = map[string]bool{}, map[string][]string{}
		for _, m := range h.B.Members() {
			out.Lines[m] = h.B.Lines(m)
			out.Wake[m] = h.B.Wake(m, ev.At)
		}
		h.W.Unlock()
		out.Projected = h.Lines(ev.At)
	default:
		return out, fmt.Errorf("home: unknown event kind %q", ev.Kind)
	}
	out.Surprises = append(out.Surprises, h.W.Surprises[n:]...)
	return out, nil
}

// Hash is a checkpoint: a digest of everything a replay must reproduce, the world, the board
// and the adapter's own state (the commands awaiting read-back, the radars, the outside readings).
// It is a sorted text walk over values (fmt prints maps sorted and a float in its shortest exact
// form, NaN included), never over pointers.
func (h *Home) Hash() string {
	h.W.Lock()
	defer h.W.Unlock()
	d := sha256.New()
	p := func(format string, a ...any) { fmt.Fprintf(d, format, a...) }
	w := h.W
	for _, id := range sortedEntries(w) {
		e := w.Entries[id]
		p("E %s %v %s %s %v\n", e.ID, e.Kind, e.Name, e.In, e.Attrs)
		for _, n := range allKeys(e.Vars) {
			p("V %s.%s %v\n", id, n, *e.Vars[n])
		}
	}
	if doc := w.Where; doc != nil {
		p("D %v %v %v %v %v %v\n", doc.Places, doc.Belief, doc.Exists, doc.Looked, doc.Gone, doc.Binding)
		for _, k := range allKeys(doc.Things) {
			p("T %s %v\n", k, *doc.Things[k])
		}
	}
	p("S %v\nN %v\n", w.Surprises, w.Now)
	p("%s", w.Taste.HashText())
	p("%s", w.Sched.HashText())
	b := h.B.State()
	p("B %v %v %v %v %v %v\n", b.Levels, b.C, b.Last, b.PV, b.Seen, b.Beat)
	for _, k := range allKeys(h.pend) {
		x := h.pend[k]
		p("P %s %s %v %s\n", k, x.value, x.deadline, x.held)
	}
	for _, k := range allKeys(h.radar) {
		p("R %s %v\n", k, *h.radar[k])
	}
	for _, k := range allKeys(h.out) {
		if o := h.out[k]; o != nil {
			p("O %s %v\n", k, *o)
		}
	}
	p("F %v %v %v %v %v\n", h.runFrom, h.feedUp, h.last, h.started, h.fans)
	return hex.EncodeToString(d.Sum(nil)[:12])
}

// allKeys: every key, sorted (keys skips the map file's "_" notes; a checkpoint skips nothing).
func allKeys[V any](m map[string]V) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}
